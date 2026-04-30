"""Tests for HTMX auto-save endpoint."""
import pytest
from tests.conftest import login
from app.models import Response, AuditLog


def test_autosave_creates_response(client, db, sample_assessment):
    login(client, "testcustomer", "custpass")
    resp = client.post(
        f"/htmx/assessments/{sample_assessment.id}/response/dod_zt.user.1.1",
        data={"current": "partial", "target": "target", "notes": "MFA mostly deployed"},
    )
    assert resp.status_code == 200
    assert b"Saved" in resp.data

    saved = Response.query.filter_by(
        assessment_id=sample_assessment.id, activity_id="dod_zt.user.1.1"
    ).first()
    assert saved is not None
    assert saved.current_state_value == "partial"
    assert saved.target_state_value == "target"
    assert saved.evidence_notes == "MFA mostly deployed"


def test_autosave_updates_response(client, db, sample_assessment):
    login(client, "testcustomer", "custpass")
    # Create first
    client.post(
        f"/htmx/assessments/{sample_assessment.id}/response/dod_zt.user.1.1",
        data={"current": "partial", "target": "target", "notes": ""},
    )
    # Update
    resp = client.post(
        f"/htmx/assessments/{sample_assessment.id}/response/dod_zt.user.1.1",
        data={"current": "target", "target": "advanced", "notes": "Updated"},
    )
    assert resp.status_code == 200

    saved = Response.query.filter_by(
        assessment_id=sample_assessment.id, activity_id="dod_zt.user.1.1"
    ).first()
    assert saved.current_state_value == "target"
    assert saved.target_state_value == "advanced"


def test_autosave_flips_status_to_in_progress(client, db, sample_assessment):
    assert sample_assessment.status == "draft"
    login(client, "testcustomer", "custpass")
    client.post(
        f"/htmx/assessments/{sample_assessment.id}/response/dod_zt.user.1.1",
        data={"current": "partial", "target": "target", "notes": ""},
    )
    from app.extensions import db as ext_db
    ext_db.session.refresh(sample_assessment)
    assert sample_assessment.status == "in_progress"


def test_autosave_creates_audit_log(client, db, sample_assessment):
    login(client, "testcustomer", "custpass")
    client.post(
        f"/htmx/assessments/{sample_assessment.id}/response/dod_zt.user.1.1",
        data={"current": "not_met", "target": "target", "notes": ""},
    )
    logs = AuditLog.query.filter_by(
        assessment_id=sample_assessment.id, target_id="dod_zt.user.1.1"
    ).all()
    assert len(logs) >= 1


def test_autosave_locked_assessment_returns_error(client, db, sample_assessment):
    sample_assessment.status = "awaiting_review"
    db.session.commit()
    login(client, "testcustomer", "custpass")
    resp = client.post(
        f"/htmx/assessments/{sample_assessment.id}/response/dod_zt.user.1.1",
        data={"current": "partial", "target": "target", "notes": ""},
    )
    assert resp.status_code == 200
    assert b"locked" in resp.data.lower()


def test_autosave_wrong_assessment_forbidden(client, db, sample_assessment):
    from app.models import Assessment
    other = Assessment(customer_org="Other", framework="dod_zt", variant="zt_only")
    db.session.add(other)
    db.session.commit()

    login(client, "testcustomer", "custpass")
    resp = client.post(
        f"/htmx/assessments/{other.id}/response/dod_zt.user.1.1",
        data={"current": "partial", "target": "target", "notes": ""},
    )
    assert resp.status_code == 200
    assert b"Access denied" in resp.data


def test_autosave_requires_login(client, sample_assessment):
    resp = client.post(
        f"/htmx/assessments/{sample_assessment.id}/response/dod_zt.user.1.1",
        data={"current": "partial", "target": "target", "notes": ""},
        follow_redirects=False,
    )
    assert resp.status_code == 302  # redirect to login


def test_autosave_sanitizes_html_in_notes(client, db, sample_assessment):
    login(client, "testcustomer", "custpass")
    client.post(
        f"/htmx/assessments/{sample_assessment.id}/response/dod_zt.user.1.1",
        data={"current": "partial", "target": "target", "notes": "<script>alert(1)</script>clean"},
    )
    saved = Response.query.filter_by(
        assessment_id=sample_assessment.id, activity_id="dod_zt.user.1.1"
    ).first()
    assert "<script>" not in (saved.evidence_notes or "")
    assert "clean" in (saved.evidence_notes or "")


def test_autosave_marks_finding_stale(client, db, sample_assessment):
    from app.models import GapFinding
    # Pre-create a finding
    finding = GapFinding(
        assessment_id=sample_assessment.id,
        pillar="user",
        activity_id="dod_zt.user.1.1",
        severity="medium",
        is_stale=False,
    )
    db.session.add(finding)
    db.session.commit()

    login(client, "testcustomer", "custpass")
    client.post(
        f"/htmx/assessments/{sample_assessment.id}/response/dod_zt.user.1.1",
        data={"current": "target", "target": "advanced", "notes": ""},
    )
    db.session.refresh(finding)
    assert finding.is_stale is True
