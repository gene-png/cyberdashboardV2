"""
Orchestrates gap finding generation: identify gaps → scrub → AI → store.

Spec §5.4 and §5.5.
"""
import time
import logging
from datetime import datetime, timezone
from typing import Generator

from flask import current_app

from ..extensions import db
from ..models import Assessment, Response, GapFinding, AICallLog, AuditLog
from .framework_loader import load_framework
from .scrub_service import scrub, rehydrate, seed_token_map
from .ai_service import build_prompt, call_anthropic

logger = logging.getLogger(__name__)

# Delay between API calls to respect rate limits
_API_DELAY_SECONDS = 0.5


def _compute_severity(gap_size: int, pillar_weight: float) -> str:
    """
    Map gap_size (integer steps) × pillar_weight to a severity label.

    score = gap_size × pillar_weight × 100
    ≥ 40  → critical
    ≥ 25  → high
    ≥ 10  → medium
    else  → low
    """
    score = gap_size * pillar_weight * 100
    if score >= 40:
        return "critical"
    if score >= 25:
        return "high"
    if score >= 10:
        return "medium"
    return "low"


def generate_findings(assessment_id: str, triggered_by_user_id: str | None = None) -> dict:
    """
    Generate (or refresh) AI findings for all gaps in the assessment.

    Returns a summary dict:
        {
            "generated": int,
            "skipped": int,
            "errors": list[str],
        }

    Marks existing findings stale=False after regeneration.
    Errors are soft: one failed AI call does not abort the whole run.
    """
    assessment = db.session.get(Assessment, assessment_id)
    if not assessment:
        raise ValueError(f"Assessment {assessment_id} not found")

    framework = load_framework(assessment.framework)
    maturity_order: dict[str, int] = framework["maturity_order"]
    maturity_labels: dict[str, str] = framework["maturity_labels"]

    api_key = current_app.config.get("ANTHROPIC_API_KEY", "")
    model = current_app.config.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")

    # Ensure token map is seeded for this assessment
    usernames = [u.username for u in assessment.users]
    seed_token_map(assessment_id, assessment.customer_org, usernames)

    # Build activity lookup
    activity_lookup: dict[str, dict] = {}
    pillar_weight_lookup: dict[str, float] = {}
    pillar_name_lookup: dict[str, str] = {}
    for pillar in framework["pillars"]:
        for activity in pillar["activities"]:
            activity_lookup[activity["id"]] = activity
            pillar_weight_lookup[activity["id"]] = pillar["weight"]
            pillar_name_lookup[activity["id"]] = pillar["name"]

    # Tools for this assessment (scrubbed inline during prompt build)
    tools = [
        {"name": t.name, "vendor": t.vendor or "", "notes": t.notes or ""}
        for t in assessment.tool_inventory
    ]

    # Existing findings indexed by activity_id
    existing_findings: dict[str, GapFinding] = {
        f.activity_id: f for f in assessment.gap_findings
    }

    generated = 0
    skipped = 0
    errors: list[str] = []

    for resp in assessment.responses:
        if not resp.current_state_value or not resp.target_state_value:
            skipped += 1
            continue

        cur_order = maturity_order.get(resp.current_state_value, 0)
        tgt_order = maturity_order.get(resp.target_state_value, 0)
        gap_size = tgt_order - cur_order

        if gap_size <= 0:
            # No gap — remove stale finding if it exists
            existing = existing_findings.get(resp.activity_id)
            if existing:
                existing.is_stale = True
            skipped += 1
            continue

        activity = activity_lookup.get(resp.activity_id)
        if not activity:
            logger.warning("Activity %s not found in framework", resp.activity_id)
            skipped += 1
            continue

        pillar_weight = pillar_weight_lookup.get(resp.activity_id, 0.15)
        pillar_name = pillar_name_lookup.get(resp.activity_id, resp.pillar)
        severity = _compute_severity(gap_size, pillar_weight)

        current_label = maturity_labels.get(resp.current_state_value, resp.current_state_value)
        target_label = maturity_labels.get(resp.target_state_value, resp.target_state_value)

        # Build prompt, scrub it
        raw_prompt = build_prompt(
            framework_name=framework["name"],
            pillar_name=pillar_name,
            activity=activity,
            current_state_label=current_label,
            target_state_label=target_label,
            evidence_notes=resp.evidence_notes,
            tools=tools,
        )
        scrubbed_prompt = scrub(assessment_id, raw_prompt)

        # Call AI (or placeholder if no API key)
        if not api_key:
            ai_result = _placeholder_response(activity, current_label, target_label)
        else:
            try:
                ai_result = call_anthropic(scrubbed_prompt, model, api_key)
            except RuntimeError as e:
                errors.append(f"{resp.activity_id}: {e}")
                logger.error("AI call failed for %s: %s", resp.activity_id, e)
                continue

        scrubbed_response = ai_result["response_text"]
        rehydrated_response = rehydrate(assessment_id, scrubbed_response)

        # Upsert gap_finding
        finding = existing_findings.get(resp.activity_id)
        if finding:
            finding.severity = severity
            finding.scrubbed_prompt = scrubbed_prompt
            finding.scrubbed_response = scrubbed_response
            finding.rehydrated_response = rehydrated_response
            finding.is_stale = False
            finding.generated_at = datetime.now(timezone.utc)
            finding.generated_by = triggered_by_user_id
        else:
            finding = GapFinding(
                assessment_id=assessment_id,
                pillar=resp.pillar,
                activity_id=resp.activity_id,
                severity=severity,
                scrubbed_prompt=scrubbed_prompt,
                scrubbed_response=scrubbed_response,
                rehydrated_response=rehydrated_response,
                is_stale=False,
                generated_at=datetime.now(timezone.utc),
                generated_by=triggered_by_user_id,
            )
            db.session.add(finding)

        # Log AI call
        ai_log = AICallLog(
            assessment_id=assessment_id,
            request_body_scrubbed=scrubbed_prompt,
            response_body_scrubbed=scrubbed_response,
            model=ai_result["model"],
            tokens_in=ai_result["tokens_in"],
            tokens_out=ai_result["tokens_out"],
            duration_ms=ai_result["duration_ms"],
        )
        db.session.add(ai_log)

        db.session.commit()
        generated += 1

        # Rate limit delay between calls
        if api_key:
            time.sleep(_API_DELAY_SECONDS)

    # Audit log entry
    audit = AuditLog(
        assessment_id=assessment_id,
        user_id=triggered_by_user_id,
        action="generate_findings",
        target_type="assessment",
        target_id=assessment_id,
        after_value=f"generated={generated} errors={len(errors)}",
    )
    db.session.add(audit)
    db.session.commit()

    return {"generated": generated, "skipped": skipped, "errors": errors}


def regenerate_finding(
    assessment_id: str,
    activity_id: str,
    triggered_by_user_id: str | None = None,
) -> GapFinding:
    """
    Regenerate the AI finding for a single activity.

    Updates the existing gap_finding row in place (does not create a new one).
    Adds a regenerate_finding audit log entry.
    """
    assessment = db.session.get(Assessment, assessment_id)
    if not assessment:
        raise ValueError(f"Assessment {assessment_id} not found")

    framework = load_framework(assessment.framework)
    maturity_order = framework["maturity_order"]
    maturity_labels = framework["maturity_labels"]

    api_key = current_app.config.get("ANTHROPIC_API_KEY", "")
    model = current_app.config.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")

    resp = Response.query.filter_by(
        assessment_id=assessment_id, activity_id=activity_id
    ).first()
    if not resp:
        raise ValueError(f"Response for {activity_id} not found")

    activity = None
    pillar_weight = 0.15
    pillar_name = resp.pillar
    for pillar in framework["pillars"]:
        for act in pillar["activities"]:
            if act["id"] == activity_id:
                activity = act
                pillar_weight = pillar["weight"]
                pillar_name = pillar["name"]
                break

    if not activity:
        raise ValueError(f"Activity {activity_id} not found in framework")

    gap_size = (
        maturity_order.get(resp.target_state_value, 0)
        - maturity_order.get(resp.current_state_value, 0)
    )
    severity = _compute_severity(max(gap_size, 0), pillar_weight)
    current_label = maturity_labels.get(resp.current_state_value, resp.current_state_value)
    target_label = maturity_labels.get(resp.target_state_value, resp.target_state_value)

    tools = [
        {"name": t.name, "vendor": t.vendor or "", "notes": t.notes or ""}
        for t in assessment.tool_inventory
    ]

    raw_prompt = build_prompt(
        framework_name=framework["name"],
        pillar_name=pillar_name,
        activity=activity,
        current_state_label=current_label,
        target_state_label=target_label,
        evidence_notes=resp.evidence_notes,
        tools=tools,
    )
    scrubbed_prompt = scrub(assessment_id, raw_prompt)

    if not api_key:
        ai_result = _placeholder_response(activity, current_label, target_label)
    else:
        ai_result = call_anthropic(scrubbed_prompt, model, api_key)

    scrubbed_response = ai_result["response_text"]
    rehydrated_response = rehydrate(assessment_id, scrubbed_response)

    finding = GapFinding.query.filter_by(
        assessment_id=assessment_id, activity_id=activity_id
    ).first()

    if finding:
        finding.severity = severity
        finding.scrubbed_prompt = scrubbed_prompt
        finding.scrubbed_response = scrubbed_response
        finding.rehydrated_response = rehydrated_response
        finding.is_stale = False
        finding.generated_at = datetime.now(timezone.utc)
        finding.generated_by = triggered_by_user_id
    else:
        finding = GapFinding(
            assessment_id=assessment_id,
            pillar=resp.pillar,
            activity_id=activity_id,
            severity=severity,
            scrubbed_prompt=scrubbed_prompt,
            scrubbed_response=scrubbed_response,
            rehydrated_response=rehydrated_response,
            is_stale=False,
            generated_at=datetime.now(timezone.utc),
            generated_by=triggered_by_user_id,
        )
        db.session.add(finding)

    ai_log = AICallLog(
        assessment_id=assessment_id,
        gap_finding_id=finding.id if hasattr(finding, "id") else None,
        request_body_scrubbed=scrubbed_prompt,
        response_body_scrubbed=scrubbed_response,
        model=ai_result["model"],
        tokens_in=ai_result["tokens_in"],
        tokens_out=ai_result["tokens_out"],
        duration_ms=ai_result["duration_ms"],
    )
    db.session.add(ai_log)

    audit = AuditLog(
        assessment_id=assessment_id,
        user_id=triggered_by_user_id,
        action="regenerate_finding",
        target_type="gap_finding",
        target_id=activity_id,
    )
    db.session.add(audit)
    db.session.commit()

    return finding


def _placeholder_response(activity: dict, current_label: str, target_label: str) -> dict:
    """Return a placeholder when no API key is configured."""
    text = (
        f"1. What's missing: This activity is currently at {current_label} but "
        f"needs to reach {target_label}. A specific implementation plan is required.\n\n"
        f"2. Options to close the gap:\n"
        f"   a. Review the activity requirements for '{activity['name']}' and "
        f"identify the missing controls.\n"
        f"   b. Engage a subject matter expert to assess current posture against "
        f"the target state criteria.\n"
        f"   c. Develop a remediation roadmap with milestones aligned to the "
        f"framework requirements.\n\n"
        f"3. Tool reconfiguration: Review your existing tools to identify whether "
        f"any can be configured to address this gap without additional procurement.\n\n"
        f"4. Estimated effort: medium\n\n"
        f"[Note: AI guidance unavailable — ANTHROPIC_API_KEY not configured.]"
    )
    return {
        "response_text": text,
        "tokens_in": 0,
        "tokens_out": 0,
        "duration_ms": 0,
        "model": "placeholder",
    }
