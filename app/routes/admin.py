import io
import json
import logging
import os
from datetime import datetime, timezone
from flask import Blueprint, render_template, redirect, url_for, request, flash, abort, send_file, current_app
from flask_login import login_required, current_user
import bleach

logger = logging.getLogger(__name__)
from ..extensions import db, limiter
from ..models import (
    Assessment, AdminScore, AuditLog, GapFinding, AICallLog, SensitiveTerm, User,
    ToolInventory, ToolActivityMapping, MappingSuggestionsLog, MappingChange,
)
from ..models.mitre_technique import MitreTechnique
from ..models.attack_coverage_run import AttackCoverageRun
from ..models.coverage_report import CoverageReport
from ..services.framework_loader import load_framework
from ..services.excel_service import build_customer_excel, build_consultant_excel
from ..services.report_generator import generate_findings, regenerate_finding
from ..services.sharepoint_service import get_client_from_config, upload_assessment_outputs
from ..services.mapping_suggester import suggest_mappings, build_mapping_prompt
from ..services.attack_mapper import get_tool_fingerprint, map_tool_to_techniques
from ..services.attack_coverage_excel import build_attack_coverage_excel, compute_coverage_matrix
from .auth import is_admin_unlocked

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


def _require_admin():
    if not is_admin_unlocked():
        return redirect(url_for("auth.admin_unlock", next=request.url))
    return None


@admin_bp.route("/assessments/<assessment_id>/review")
@login_required
def review(assessment_id):
    redir = _require_admin()
    if redir:
        return redir
    assessment = db.session.get(Assessment, assessment_id)
    if not assessment:
        abort(404)
    framework = load_framework(assessment.framework)
    responses = {r.activity_id: r for r in assessment.responses}
    admin_scores = {s.pillar: s for s in assessment.admin_scores}
    return render_template(
        "admin/review.html",
        assessment=assessment,
        framework=framework,
        responses=responses,
        admin_scores=admin_scores,
        admin_unlocked=True,
    )


@admin_bp.route("/assessments/<assessment_id>/score", methods=["POST"])
@login_required
def save_scores(assessment_id):
    redir = _require_admin()
    if redir:
        return redir
    assessment = db.session.get(Assessment, assessment_id)
    if not assessment:
        abort(404)
    framework = load_framework(assessment.framework)

    for pillar in framework["pillars"]:
        pid = pillar["id"]
        current_score = request.form.get(f"current_score_{pid}", type=float)
        target_score = request.form.get(f"target_score_{pid}", type=float)
        gap_summary = request.form.get(f"gap_summary_{pid}", "").strip()
        consultant_rec = request.form.get(f"consultant_recommendation_{pid}", "").strip()

        score = AdminScore.query.filter_by(assessment_id=assessment_id, pillar=pid).first()
        if score:
            score.current_score = current_score
            score.target_score = target_score
            score.gap_summary = gap_summary
            score.consultant_recommendation = consultant_rec
        else:
            score = AdminScore(
                assessment_id=assessment_id,
                pillar=pid,
                current_score=current_score,
                target_score=target_score,
                gap_summary=gap_summary,
                consultant_recommendation=consultant_rec,
            )
            db.session.add(score)

    db.session.commit()
    flash("Admin scores saved.", "success")
    return redirect(url_for("admin.review", assessment_id=assessment_id))


@admin_bp.route("/assessments/<assessment_id>/export/customer")
@login_required
def export_customer(assessment_id):
    redir = _require_admin()
    if redir:
        return redir
    assessment = db.session.get(Assessment, assessment_id)
    if not assessment:
        abort(404)
    xlsx_bytes = build_customer_excel(assessment)
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    filename = f"{assessment.customer_org.replace(' ', '_')}_{date_str}_customer_report.xlsx"
    return send_file(
        io.BytesIO(xlsx_bytes),
        as_attachment=True,
        download_name=filename,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@admin_bp.route("/assessments/<assessment_id>/export/consultant")
@login_required
def export_consultant(assessment_id):
    redir = _require_admin()
    if redir:
        return redir
    assessment = db.session.get(Assessment, assessment_id)
    if not assessment:
        abort(404)
    xlsx_bytes = build_consultant_excel(assessment)
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    filename = f"{assessment.customer_org.replace(' ', '_')}_{date_str}_consultant_report.xlsx"
    return send_file(
        io.BytesIO(xlsx_bytes),
        as_attachment=True,
        download_name=filename,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@admin_bp.route("/assessments/<assessment_id>/finalize", methods=["POST"])
@login_required
def finalize(assessment_id):
    redir = _require_admin()
    if redir:
        return redir
    assessment = db.session.get(Assessment, assessment_id)
    if not assessment:
        abort(404)

    now = datetime.now(timezone.utc)
    assessment.status = "finalized"
    assessment.finalized_at = now

    log = AuditLog(
        assessment_id=assessment_id,
        user_id=current_user.id,
        action="finalize",
        target_type="assessment",
        target_id=assessment_id,
    )
    db.session.add(log)
    db.session.commit()

    # Build Excel files
    customer_xlsx = build_customer_excel(assessment)
    consultant_xlsx = build_consultant_excel(assessment)

    # Build response snapshot JSON
    responses_snapshot = [
        {
            "activity_id": r.activity_id,
            "pillar": r.pillar,
            "current_state_value": r.current_state_value,
            "target_state_value": r.target_state_value,
            "evidence_notes": r.evidence_notes,
        }
        for r in assessment.responses
    ]

    # Build audit CSV rows
    ai_log_rows = [
        {
            "timestamp": str(l.timestamp),
            "model": l.model,
            "tokens_in": l.tokens_in,
            "tokens_out": l.tokens_out,
            "duration_ms": l.duration_ms,
            "request_body_scrubbed": l.request_body_scrubbed or "",
            "response_body_scrubbed": l.response_body_scrubbed or "",
        }
        for l in assessment.ai_call_logs
    ]
    audit_rows = [
        {
            "timestamp": str(l.timestamp),
            "user_id": l.user_id or "",
            "action": l.action,
            "target_type": l.target_type or "",
            "target_id": l.target_id or "",
            "before_value": l.before_value or "",
            "after_value": l.after_value or "",
        }
        for l in assessment.audit_logs
    ]

    # Upload to SharePoint (no-op if not configured)
    sp_client = get_client_from_config(current_app.config)
    if sp_client:
        try:
            upload_assessment_outputs(
                client=sp_client,
                assessment_id=assessment_id,
                org_name=assessment.customer_org,
                finalized_at=now,
                customer_xlsx=customer_xlsx,
                consultant_xlsx=consultant_xlsx,
                responses_json=json.dumps(responses_snapshot, indent=2),
                ai_call_log_rows=ai_log_rows,
                audit_log_rows=audit_rows,
            )
            flash("Assessment finalized and uploaded to SharePoint.", "success")
        except Exception as e:
            flash(f"Assessment finalized but SharePoint upload failed: {e}", "warning")
    else:
        flash("Assessment finalized. (SharePoint not configured — download exports manually.)", "success")

    return redirect(url_for("admin.review", assessment_id=assessment_id))


@admin_bp.route("/assessments/<assessment_id>/reopen", methods=["POST"])
@login_required
def reopen(assessment_id):
    redir = _require_admin()
    if redir:
        return redir
    assessment = db.session.get(Assessment, assessment_id)
    if not assessment:
        abort(404)
    assessment.status = "reopened"
    log = AuditLog(
        assessment_id=assessment_id,
        user_id=current_user.id,
        action="reopen",
        target_type="assessment",
        target_id=assessment_id,
    )
    db.session.add(log)
    db.session.commit()
    flash("Assessment reopened.", "success")
    return redirect(url_for("admin.review", assessment_id=assessment_id))


@admin_bp.route("/assessments/<assessment_id>/findings")
@login_required
def findings(assessment_id):
    redir = _require_admin()
    if redir:
        return redir
    assessment = db.session.get(Assessment, assessment_id)
    if not assessment:
        abort(404)
    framework = load_framework(assessment.framework)

    # Build activity lookup for display names
    activity_lookup: dict = {}
    pillar_name_lookup: dict = {}
    for pillar in framework["pillars"]:
        for activity in pillar["activities"]:
            activity_lookup[activity["id"]] = activity
            pillar_name_lookup[activity["id"]] = pillar["name"]

    gap_findings = (
        GapFinding.query
        .filter_by(assessment_id=assessment_id)
        .order_by(GapFinding.pillar, GapFinding.activity_id)
        .all()
    )
    return render_template(
        "admin/findings.html",
        assessment=assessment,
        framework=framework,
        gap_findings=gap_findings,
        activity_lookup=activity_lookup,
        pillar_name_lookup=pillar_name_lookup,
        admin_unlocked=True,
    )


@admin_bp.route("/assessments/<assessment_id>/generate", methods=["POST"])
@login_required
def generate(assessment_id):
    redir = _require_admin()
    if redir:
        return redir
    assessment = db.session.get(Assessment, assessment_id)
    if not assessment:
        abort(404)

    try:
        result = generate_findings(assessment_id, triggered_by_user_id=current_user.id)
        msg = f"AI findings generated: {result['generated']} gaps processed."
        if result["errors"]:
            msg += f" {len(result['errors'])} errors — check logs."
            flash(msg, "warning")
        else:
            flash(msg, "success")
    except Exception as e:
        flash(f"Generation failed: {e}", "danger")

    return redirect(url_for("admin.findings", assessment_id=assessment_id))


@admin_bp.route("/assessments/<assessment_id>/findings/<activity_id>/regenerate", methods=["POST"])
@login_required
@limiter.limit("10 per minute")
def regenerate(assessment_id, activity_id):
    redir = _require_admin()
    if redir:
        return redir
    assessment = db.session.get(Assessment, assessment_id)
    if not assessment:
        abort(404)

    try:
        regenerate_finding(assessment_id, activity_id, triggered_by_user_id=current_user.id)
        flash(f"Finding for {activity_id} regenerated.", "success")
    except Exception as e:
        flash(f"Regeneration failed: {e}", "danger")

    return redirect(url_for("admin.findings", assessment_id=assessment_id))


@admin_bp.route("/assessments/<assessment_id>/audit")
@login_required
def audit_log(assessment_id):
    redir = _require_admin()
    if redir:
        return redir
    assessment = db.session.get(Assessment, assessment_id)
    if not assessment:
        abort(404)

    logs = (
        AuditLog.query
        .filter_by(assessment_id=assessment_id)
        .order_by(AuditLog.timestamp.desc())
        .all()
    )
    user_map = {u.id: u.username for u in User.query.all()}
    return render_template(
        "admin/audit.html",
        assessment=assessment,
        logs=logs,
        user_map=user_map,
        admin_unlocked=True,
    )


@admin_bp.route("/assessments/<assessment_id>/terms", methods=["GET", "POST"])
@login_required
def sensitive_terms(assessment_id):
    redir = _require_admin()
    if redir:
        return redir
    assessment = db.session.get(Assessment, assessment_id)
    if not assessment:
        abort(404)

    if request.method == "POST":
        action = request.form.get("action", "add")

        if action == "add":
            raw_term = request.form.get("term", "").strip()
            term = bleach.clean(raw_term, tags=[], strip=True)
            if term:
                # Generate a sequential token name
                existing_user_count = SensitiveTerm.query.filter_by(
                    assessment_id=assessment_id, source="user_added"
                ).count()
                token = f"[CUSTOM_{existing_user_count + 1}]"
                st = SensitiveTerm(
                    assessment_id=assessment_id,
                    term=term,
                    replacement_token=token,
                    source="user_added",
                    is_active=True,
                )
                db.session.add(st)
                log = AuditLog(
                    assessment_id=assessment_id,
                    user_id=current_user.id,
                    action="add_sensitive_term",
                    target_type="sensitive_term",
                    target_id=token,
                    after_value=term,
                )
                db.session.add(log)
                db.session.commit()
                flash(f"Term added and mapped to {token}.", "success")
            else:
                flash("Term cannot be empty.", "warning")

        elif action == "deactivate":
            term_id = request.form.get("term_id", "").strip()
            st = db.session.get(SensitiveTerm, term_id)
            if st and st.assessment_id == assessment_id:
                st.is_active = False
                log = AuditLog(
                    assessment_id=assessment_id,
                    user_id=current_user.id,
                    action="deactivate_sensitive_term",
                    target_type="sensitive_term",
                    target_id=st.replacement_token,
                    before_value=st.term,
                )
                db.session.add(log)
                db.session.commit()
                flash(f"Term '{st.term}' deactivated.", "success")
            else:
                flash("Term not found.", "warning")

        return redirect(url_for("admin.sensitive_terms", assessment_id=assessment_id))

    terms = (
        SensitiveTerm.query
        .filter_by(assessment_id=assessment_id)
        .order_by(SensitiveTerm.source, SensitiveTerm.term)
        .all()
    )
    return render_template(
        "admin/terms.html",
        assessment=assessment,
        terms=terms,
        admin_unlocked=True,
    )


# ---------------------------------------------------------------------------
# Tool Activity Mapping
# ---------------------------------------------------------------------------

@admin_bp.route("/assessments/<assessment_id>/inventory/<tool_id>/mapping")
@login_required
def tool_mapping(assessment_id, tool_id):
    redir = _require_admin()
    if redir:
        return redir
    assessment = db.session.get(Assessment, assessment_id)
    if not assessment:
        abort(404)
    tool = db.session.get(ToolInventory, tool_id)
    if not tool or tool.assessment_id != assessment_id:
        abort(404)

    framework = load_framework(assessment.framework)

    # Build dict of existing mappings: activity_id → ToolActivityMapping
    existing_mappings = {m.activity_id: m for m in tool.activity_mappings}

    # Build dict of AI suggestions (only ai_suggested rows)
    ai_suggestions = {
        m.activity_id: m for m in tool.activity_mappings if m.source == "ai_suggested"
    }
    # Confirmed/admin-added also exist after finalization
    confirmed_ids = {
        m.activity_id for m in tool.activity_mappings
        if m.source in ("admin_confirmed", "admin_added")
    }

    ai_count = len(ai_suggestions)
    mapped_count = len(confirmed_ids)

    return render_template(
        "admin/tool_mapping.html",
        assessment=assessment,
        tool=tool,
        framework=framework,
        existing_mappings=existing_mappings,
        ai_suggestions=ai_suggestions,
        confirmed_ids=confirmed_ids,
        ai_count=ai_count,
        mapped_count=mapped_count,
        admin_unlocked=True,
    )


@admin_bp.route("/assessments/<assessment_id>/inventory/<tool_id>/mapping/suggest", methods=["POST"])
@login_required
def tool_mapping_suggest(assessment_id, tool_id):
    redir = _require_admin()
    if redir:
        return redir
    assessment = db.session.get(Assessment, assessment_id)
    if not assessment:
        abort(404)
    tool = db.session.get(ToolInventory, tool_id)
    if not tool or tool.assessment_id != assessment_id:
        abort(404)

    framework = load_framework(assessment.framework)
    api_key = current_app.config.get("ANTHROPIC_API_KEY", "")
    model = current_app.config.get("MAPPING_MODEL", "claude-sonnet-4-6")

    result = suggest_mappings(tool, framework, api_key, model)

    # suggest_mappings returns (suggestions, error) or (suggestions, None, prompt, raw, model)
    if len(result) == 2:
        suggestions, error = result
        prompt_text, raw_response, used_model = "", "", model
    else:
        suggestions, error, prompt_text, raw_response, used_model = result

    # Log the call regardless of success
    log_entry = MappingSuggestionsLog(
        tool_id=tool.id,
        assessment_id=assessment_id,
        request_payload=prompt_text[:10000] if prompt_text else "",
        response_payload=raw_response[:10000] if raw_response else (error or ""),
        model_used=used_model,
    )
    db.session.add(log_entry)

    if error:
        flash(f"AI suggestions unavailable — map manually. ({error})", "warning")
    else:
        # Replace existing ai_suggested mappings for this tool
        ToolActivityMapping.query.filter_by(tool_id=tool.id, source="ai_suggested").delete()

        for s in suggestions:
            mapping = ToolActivityMapping(
                tool_id=tool.id,
                activity_id=s["activity_id"],
                source="ai_suggested",
                ai_confidence=s.get("confidence"),
                ai_rationale=s.get("rationale"),
            )
            db.session.add(mapping)

        flash(f"AI suggested {len(suggestions)} activity mappings. Review and finalize below.", "success")

    db.session.commit()
    return redirect(url_for("admin.tool_mapping", assessment_id=assessment_id, tool_id=tool_id))


@admin_bp.route("/assessments/<assessment_id>/inventory/<tool_id>/mapping/finalize", methods=["POST"])
@login_required
def tool_mapping_finalize(assessment_id, tool_id):
    redir = _require_admin()
    if redir:
        return redir
    assessment = db.session.get(Assessment, assessment_id)
    if not assessment:
        abort(404)
    tool = db.session.get(ToolInventory, tool_id)
    if not tool or tool.assessment_id != assessment_id:
        abort(404)

    checked_ids = set(request.form.getlist("activity_ids"))
    if not checked_ids:
        flash("Select at least one activity before finalizing.", "warning")
        return redirect(url_for("admin.tool_mapping", assessment_id=assessment_id, tool_id=tool_id))

    # Capture before-state for audit
    before_ids = sorted(
        m.activity_id for m in tool.activity_mappings
        if m.source in ("admin_confirmed", "admin_added")
    )
    already_finalized = tool.mapping_status == "active"

    # Get the AI-suggested set for source classification
    ai_suggested_ids = {
        m.activity_id for m in tool.activity_mappings if m.source == "ai_suggested"
    }

    # Replace all non-ai_suggested mappings
    ToolActivityMapping.query.filter(
        ToolActivityMapping.tool_id == tool.id,
        ToolActivityMapping.source.in_(["admin_confirmed", "admin_added"]),
    ).delete(synchronize_session=False)

    # Also remove ai_suggested rows so we replace them with confirmed/added
    ToolActivityMapping.query.filter_by(tool_id=tool.id, source="ai_suggested").delete(
        synchronize_session=False
    )

    # Get AI rationales from existing suggestion log for confirmed activities
    latest_log = (
        MappingSuggestionsLog.query
        .filter_by(tool_id=tool.id)
        .order_by(MappingSuggestionsLog.created_at.desc())
        .first()
    )
    ai_rationale_map: dict[str, str] = {}
    if latest_log and latest_log.response_payload:
        try:
            items = json.loads(latest_log.response_payload)
            if isinstance(items, list):
                for item in items:
                    if isinstance(item, dict) and "activity_id" in item:
                        ai_rationale_map[item["activity_id"]] = item.get("rationale", "")
        except (json.JSONDecodeError, Exception):
            pass

    # Also build confidence map from existing ai_suggested rows (still in session)
    ai_conf_map: dict[str, str] = {}
    for m in tool.activity_mappings:
        if m.source == "ai_suggested" and m.ai_confidence:
            ai_conf_map[m.activity_id] = m.ai_confidence

    for aid in checked_ids:
        source = "admin_confirmed" if aid in ai_suggested_ids else "admin_added"
        mapping = ToolActivityMapping(
            tool_id=tool.id,
            activity_id=aid,
            source=source,
            ai_confidence=ai_conf_map.get(aid) if source == "admin_confirmed" else None,
            ai_rationale=ai_rationale_map.get(aid) if source == "admin_confirmed" else None,
        )
        db.session.add(mapping)

    now = datetime.now(timezone.utc)
    tool.mapping_status = "active"
    tool.mappings_finalized_at = now
    tool.mappings_finalized_by = current_user.id

    # Audit trail for post-finalization edits
    if already_finalized:
        change = MappingChange(
            tool_id=tool.id,
            assessment_id=assessment_id,
            user_id=current_user.id,
            before_state=json.dumps(before_ids),
            after_state=json.dumps(sorted(checked_ids)),
        )
        db.session.add(change)

    db.session.commit()
    flash(f"Mappings finalized. {len(checked_ids)} activities mapped for {tool.name}.", "success")
    return redirect(url_for("admin.tool_mapping", assessment_id=assessment_id, tool_id=tool_id))


# ---------------------------------------------------------------------------
# ATT&CK Coverage Report
# ---------------------------------------------------------------------------

@admin_bp.route("/assessments/<assessment_id>/attack-coverage")
@login_required
def attack_coverage(assessment_id):
    redir = _require_admin()
    if redir:
        return redir
    assessment = db.session.get(Assessment, assessment_id)
    if not assessment:
        abort(404)

    tools = assessment.tool_inventory
    pending_tools = [t for t in tools if t.mapping_status == "pending_review"]
    active_tools = [t for t in tools if t.mapping_status == "active"]
    has_techniques = MitreTechnique.query.limit(1).count() > 0

    past_reports = (
        CoverageReport.query
        .filter_by(assessment_id=assessment_id)
        .order_by(CoverageReport.generated_at.desc())
        .all()
    )

    recent_report = None
    if past_reports:
        age = datetime.now(timezone.utc) - past_reports[0].generated_at.replace(tzinfo=timezone.utc)
        if age.total_seconds() < 86400:  # 24h
            recent_report = past_reports[0]

    return render_template(
        "admin/attack_coverage.html",
        assessment=assessment,
        pending_tools=pending_tools,
        active_tools=active_tools,
        past_reports=past_reports,
        recent_report=recent_report,
        has_techniques=has_techniques,
        admin_unlocked=True,
    )


@admin_bp.route("/assessments/<assessment_id>/attack-coverage/generate", methods=["POST"])
@login_required
def attack_coverage_generate(assessment_id):
    redir = _require_admin()
    if redir:
        return redir
    assessment = db.session.get(Assessment, assessment_id)
    if not assessment:
        abort(404)

    active_tools = [t for t in assessment.tool_inventory if t.mapping_status == "active"]
    excluded_names = [t.name for t in assessment.tool_inventory if t.mapping_status == "pending_review"]

    if not active_tools:
        flash("No tools with finalized mappings. Map and finalize tools before generating the report.", "warning")
        return redirect(url_for("admin.attack_coverage", assessment_id=assessment_id))

    techniques = MitreTechnique.query.all()
    if not techniques:
        flash(
            "MITRE ATT&CK technique database is empty. "
            "Run 'python scripts/seed_mitre.py' to load techniques first.",
            "warning",
        )
        return redirect(url_for("admin.attack_coverage", assessment_id=assessment_id))

    api_key = current_app.config.get("ANTHROPIC_API_KEY", "")
    model = current_app.config.get("ATTACK_MODEL", current_app.config.get("ANTHROPIC_MODEL", "claude-sonnet-4-6"))

    coverage_data = []
    errors = []

    for tool in active_tools:
        activity_ids = [m.activity_id for m in tool.active_mappings]
        fingerprint = get_tool_fingerprint(tool, activity_ids)

        # Check cache
        cached = (
            AttackCoverageRun.query
            .filter_by(tool_id=tool.id, tool_fingerprint=fingerprint)
            .order_by(AttackCoverageRun.created_at.desc())
            .first()
        )

        results, error = map_tool_to_techniques(
            tool, activity_ids, techniques, api_key, model, cached_run=cached
        )

        if error:
            errors.append(f"{tool.name}: {error}")
            if not api_key:
                break  # No point continuing if API key is missing
        else:
            # Cache new result if it wasn't a cache hit
            if not (cached and cached.tool_fingerprint == fingerprint):
                run = AttackCoverageRun(
                    assessment_id=assessment_id,
                    tool_id=tool.id,
                    tool_fingerprint=fingerprint,
                    response_payload=json.dumps(results),
                    model_used=model,
                )
                db.session.add(run)
                db.session.commit()

        coverage_data.append({"tool": tool, "activity_ids": activity_ids, "results": results})

    if errors and not any(d["results"] for d in coverage_data):
        flash(f"Report generation failed: {'; '.join(errors)}", "danger")
        return redirect(url_for("admin.attack_coverage", assessment_id=assessment_id))

    if errors:
        flash(f"Partial report — some tools failed: {'; '.join(errors)}", "warning")

    # Build Excel
    now = datetime.now(timezone.utc)
    xlsx_bytes = build_attack_coverage_excel(
        coverage_data=coverage_data,
        techniques=techniques,
        generated_at=now,
        model_used=model,
        excluded_tool_names=excluded_names,
    )

    # Save to REPORTS_DIR
    reports_dir = current_app.config.get("REPORTS_DIR", os.path.join(current_app.instance_path, "reports"))
    os.makedirs(reports_dir, exist_ok=True)
    timestamp_str = now.strftime("%Y%m%d_%H%M%S")
    filename = f"attack_coverage_{assessment_id[:8]}_{timestamp_str}.xlsx"
    file_path = os.path.join(reports_dir, filename)
    with open(file_path, "wb") as fh:
        fh.write(xlsx_bytes)

    # Compute covered count from matrix
    matrix = compute_coverage_matrix(coverage_data, techniques)
    covered_count = sum(1 for v in matrix.values() if v["gap_status"] != "None")

    report = CoverageReport(
        assessment_id=assessment_id,
        generated_by=current_user.id,
        generated_at=now,
        tool_count=len(active_tools),
        technique_count=len(techniques),
        covered_count=covered_count,
        file_path=file_path,
        model_used=model,
    )
    db.session.add(report)
    db.session.commit()

    flash(
        f"ATT&CK Coverage Report generated: {len(active_tools)} tools, "
        f"{covered_count}/{len(techniques)} techniques covered.",
        "success",
    )
    return redirect(url_for("admin.attack_coverage", assessment_id=assessment_id))


@admin_bp.route("/assessments/<assessment_id>/attack-coverage/<report_id>/download")
@login_required
def attack_coverage_download(assessment_id, report_id):
    redir = _require_admin()
    if redir:
        return redir
    report = db.session.get(CoverageReport, report_id)
    if not report or report.assessment_id != assessment_id:
        abort(404)

    if not os.path.exists(report.file_path):
        flash("Report file not found on disk. It may have been removed.", "danger")
        return redirect(url_for("admin.attack_coverage", assessment_id=assessment_id))

    filename = f"attack_coverage_{report.generated_at.strftime('%Y-%m-%d')}.xlsx"
    return send_file(
        report.file_path,
        as_attachment=True,
        download_name=filename,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@admin_bp.route("/assessments/<assessment_id>/inventory/map-all", methods=["POST"])
def bulk_map_tools(assessment_id):
    redir = _require_admin()
    if redir:
        return redir

    assessment = db.session.get(Assessment, assessment_id)
    if not assessment:
        abort(404)

    api_key = current_app.config.get("ANTHROPIC_API_KEY", "")
    model = current_app.config.get("MAPPING_MODEL", current_app.config.get("ANTHROPIC_MODEL", "claude-sonnet-4-6"))

    tools = [t for t in assessment.tool_inventory if t.mapping_status != "active"]
    if not tools:
        flash("All tools already have active mappings.", "info")
        return redirect(url_for("assessment.inventory", assessment_id=assessment_id))

    if not api_key:
        flash("ANTHROPIC_API_KEY not configured — cannot run AI mapping.", "warning")
        return redirect(url_for("assessment.inventory", assessment_id=assessment_id))

    framework = load_framework(assessment.framework)
    mapped = 0
    errors = []
    for tool in tools:
        try:
            result = suggest_mappings(tool, framework, api_key, model)
            if len(result) == 2:
                suggestions, error = result
            else:
                suggestions, error = result[0], result[1]

            log_entry = MappingSuggestionsLog(
                tool_id=tool.id,
                assessment_id=assessment_id,
                request_payload="bulk_map",
                response_payload=str(error or f"{len(suggestions)} suggestions"),
                model_used=model,
            )
            db.session.add(log_entry)

            if error:
                errors.append(f"{tool.name}: {error}")
            else:
                ToolActivityMapping.query.filter_by(tool_id=tool.id, source="ai_suggested").delete()
                for s in suggestions:
                    mapping = ToolActivityMapping(
                        tool_id=tool.id,
                        activity_id=s["activity_id"],
                        source="ai_suggested",
                        ai_confidence=s.get("confidence"),
                        ai_rationale=s.get("rationale"),
                    )
                    db.session.add(mapping)
                mapped += 1

            db.session.commit()
        except Exception as exc:
            errors.append(f"{tool.name}: {exc}")
            logger.warning("Bulk map failed for tool %s: %s", tool.id, exc)

    if errors:
        flash(f"Mapped {mapped} tool(s). {len(errors)} error(s): {'; '.join(errors[:3])}", "warning")
    else:
        flash(f"AI mapping complete — {mapped} tool(s) queued for review.", "success")

    return redirect(url_for("assessment.inventory", assessment_id=assessment_id))
