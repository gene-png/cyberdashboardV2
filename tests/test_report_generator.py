"""Tests for report_generator — uses placeholder AI (no API key needed)."""
import pytest
from app.models import Assessment, User, Response, GapFinding, AICallLog, AuditLog
from app.services.report_generator import generate_findings, regenerate_finding, _compute_severity


@pytest.fixture
def assessment_with_gaps(db):
    a = Assessment(
        customer_org="Gap Test Corp",
        framework="dod_zt",
        variant="zt_only",
        status="awaiting_review",
    )
    db.session.add(a)
    db.session.flush()

    u = User(username="gapcustomer", role="customer", assessment_id=a.id)
    u.set_password("pw")
    db.session.add(u)

    # Two gaps, one no-gap
    responses = [
        Response(assessment_id=a.id, pillar="user", activity_id="dod_zt.user.1.1",
                 current_state_value="not_met", target_state_value="target"),
        Response(assessment_id=a.id, pillar="user", activity_id="dod_zt.user.1.2",
                 current_state_value="partial", target_state_value="advanced"),
        Response(assessment_id=a.id, pillar="device", activity_id="dod_zt.device.2.1",
                 current_state_value="target", target_state_value="target"),  # no gap
    ]
    for r in responses:
        db.session.add(r)
    db.session.commit()
    return a


# ---- Severity formula ----

def test_severity_critical():
    # gap=3, weight=0.20 → score=60 → critical
    assert _compute_severity(3, 0.20) == "critical"


def test_severity_high():
    # gap=2, weight=0.20 → score=40 → critical threshold
    # gap=2, weight=0.15 → score=30 → high
    assert _compute_severity(2, 0.15) == "high"


def test_severity_medium():
    # gap=1, weight=0.15 → score=15 → medium
    assert _compute_severity(1, 0.15) == "medium"


def test_severity_low():
    # gap=1, weight=0.05 → score=5 → low
    assert _compute_severity(1, 0.05) == "low"


# ---- generate_findings ----

def test_generate_creates_findings(app, assessment_with_gaps):
    with app.app_context():
        result = generate_findings(assessment_with_gaps.id)
    assert result["generated"] == 2   # two gaps
    assert result["skipped"] >= 1     # one no-gap response
    assert result["errors"] == []


def test_generate_stores_findings_in_db(db, app, assessment_with_gaps):
    with app.app_context():
        generate_findings(assessment_with_gaps.id)
    findings = GapFinding.query.filter_by(assessment_id=assessment_with_gaps.id).all()
    assert len(findings) == 2
    for f in findings:
        assert f.rehydrated_response is not None
        assert f.severity in ("low", "medium", "high", "critical")
        assert f.is_stale is False


def test_scrubbed_prompt_redacts_evidence_notes(db, app, assessment_with_gaps):
    """Evidence notes containing the org name must be scrubbed before storage."""
    # Add evidence notes with the org name
    resp = Response.query.filter_by(
        assessment_id=assessment_with_gaps.id, activity_id="dod_zt.user.1.1"
    ).first()
    resp.evidence_notes = "Gap Test Corp has deployed Duo MFA for 60% of users."
    db.session.commit()

    with app.app_context():
        generate_findings(assessment_with_gaps.id)

    finding = GapFinding.query.filter_by(
        assessment_id=assessment_with_gaps.id, activity_id="dod_zt.user.1.1"
    ).first()
    assert finding is not None
    assert "Gap Test Corp" not in finding.scrubbed_prompt
    assert "[ORG_" in finding.scrubbed_prompt




def test_generate_logs_ai_calls(db, app, assessment_with_gaps):
    with app.app_context():
        generate_findings(assessment_with_gaps.id)
    logs = AICallLog.query.filter_by(assessment_id=assessment_with_gaps.id).all()
    assert len(logs) == 2


def test_generate_logs_audit(db, app, assessment_with_gaps):
    with app.app_context():
        generate_findings(assessment_with_gaps.id)
    logs = AuditLog.query.filter_by(
        assessment_id=assessment_with_gaps.id, action="generate_findings"
    ).all()
    assert len(logs) == 1


def test_generate_idempotent(db, app, assessment_with_gaps):
    """Running generate twice should update findings, not create duplicates."""
    with app.app_context():
        generate_findings(assessment_with_gaps.id)
        generate_findings(assessment_with_gaps.id)
    findings = GapFinding.query.filter_by(assessment_id=assessment_with_gaps.id).all()
    assert len(findings) == 2  # not 4


def test_generate_marks_no_gap_stale(db, app, assessment_with_gaps):
    """If a finding exists for an activity that no longer has a gap, mark it stale."""
    # Create a finding for the no-gap activity
    stale_finding = GapFinding(
        assessment_id=assessment_with_gaps.id,
        pillar="device",
        activity_id="dod_zt.device.2.1",
        severity="medium",
        rehydrated_response="old guidance",
        is_stale=False,
    )
    db.session.add(stale_finding)
    db.session.commit()

    with app.app_context():
        generate_findings(assessment_with_gaps.id)

    db.session.refresh(stale_finding)
    assert stale_finding.is_stale is True


# ---- regenerate_finding ----

def test_regenerate_updates_existing(db, app, assessment_with_gaps):
    with app.app_context():
        generate_findings(assessment_with_gaps.id)

    finding_before = GapFinding.query.filter_by(
        assessment_id=assessment_with_gaps.id, activity_id="dod_zt.user.1.1"
    ).first()
    old_text = finding_before.rehydrated_response

    with app.app_context():
        regenerate_finding(assessment_with_gaps.id, "dod_zt.user.1.1")

    finding_after = GapFinding.query.filter_by(
        assessment_id=assessment_with_gaps.id, activity_id="dod_zt.user.1.1"
    ).first()
    # Should still be one row, not two
    count = GapFinding.query.filter_by(
        assessment_id=assessment_with_gaps.id, activity_id="dod_zt.user.1.1"
    ).count()
    assert count == 1
    assert finding_after.is_stale is False


def test_regenerate_logs_audit(db, app, assessment_with_gaps):
    with app.app_context():
        generate_findings(assessment_with_gaps.id)
        regenerate_finding(assessment_with_gaps.id, "dod_zt.user.1.1")

    logs = AuditLog.query.filter_by(
        assessment_id=assessment_with_gaps.id, action="regenerate_finding"
    ).all()
    assert len(logs) == 1


def test_regenerate_nonexistent_response_raises(app, assessment_with_gaps):
    with app.app_context():
        with pytest.raises(ValueError, match="Response for .* not found"):
            regenerate_finding(assessment_with_gaps.id, "dod_zt.user.9.9")
