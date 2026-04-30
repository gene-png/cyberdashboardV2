"""Tests for admin audit log and sensitive terms views."""
import pytest
from datetime import datetime, timezone
from tests.conftest import login
from app.models import Assessment, AuditLog, SensitiveTerm, User
from app.extensions import db as ext_db


def _unlock_admin(client):
    with client.session_transaction() as sess:
        sess["admin_unlocked_at"] = datetime.now(timezone.utc).isoformat()


# ---- Fixtures ----

@pytest.fixture
def admin_assessment(db, admin_user):
    a = Assessment(
        customer_org="Admin Test Org",
        framework="dod_zt",
        variant="zt_only",
        status="in_progress",
    )
    db.session.add(a)
    db.session.commit()
    return a


# ---- Audit log view ----

def test_audit_log_requires_admin_unlock(client, admin_user, admin_assessment):
    login(client, "admin", "adminpass")
    # No admin unlock — should redirect
    resp = client.get(
        f"/admin/assessments/{admin_assessment.id}/audit",
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert "/admin/unlock" in resp.headers["Location"]


def test_audit_log_empty(client, db, admin_user, admin_assessment):
    login(client, "admin", "adminpass")
    _unlock_admin(client)
    resp = client.get(f"/admin/assessments/{admin_assessment.id}/audit")
    assert resp.status_code == 200
    assert b"No audit log" in resp.data


def test_audit_log_shows_entries(client, db, admin_user, admin_assessment):
    log = AuditLog(
        assessment_id=admin_assessment.id,
        user_id=admin_user.id,
        action="finalize",
        target_type="assessment",
        target_id=admin_assessment.id,
    )
    db.session.add(log)
    db.session.commit()

    login(client, "admin", "adminpass")
    _unlock_admin(client)
    resp = client.get(f"/admin/assessments/{admin_assessment.id}/audit")
    assert resp.status_code == 200
    assert b"finalize" in resp.data


def test_audit_log_newest_first(client, db, admin_user, admin_assessment):
    from datetime import timedelta
    old_time = datetime.now(timezone.utc) - timedelta(hours=1)
    new_time = datetime.now(timezone.utc)

    log_old = AuditLog(
        assessment_id=admin_assessment.id,
        user_id=admin_user.id,
        action="reopen",
        target_type="assessment",
        target_id=admin_assessment.id,
        timestamp=old_time,
    )
    log_new = AuditLog(
        assessment_id=admin_assessment.id,
        user_id=admin_user.id,
        action="finalize",
        target_type="assessment",
        target_id=admin_assessment.id,
        timestamp=new_time,
    )
    db.session.add_all([log_old, log_new])
    db.session.commit()

    login(client, "admin", "adminpass")
    _unlock_admin(client)
    resp = client.get(f"/admin/assessments/{admin_assessment.id}/audit")
    assert resp.status_code == 200
    # "finalize" should appear before "reopen" in the response
    data = resp.data.decode()
    assert data.index("finalize") < data.index("reopen")


def test_audit_log_shows_username(client, db, admin_user, admin_assessment):
    log = AuditLog(
        assessment_id=admin_assessment.id,
        user_id=admin_user.id,
        action="save_scores",
        target_type="assessment",
        target_id=admin_assessment.id,
    )
    db.session.add(log)
    db.session.commit()

    login(client, "admin", "adminpass")
    _unlock_admin(client)
    resp = client.get(f"/admin/assessments/{admin_assessment.id}/audit")
    assert b"admin" in resp.data  # username shown


def test_audit_log_404_on_missing(client, db, admin_user):
    login(client, "admin", "adminpass")
    _unlock_admin(client)
    resp = client.get("/admin/assessments/nonexistent-id/audit")
    assert resp.status_code == 404


# ---- Sensitive terms view ----

def test_terms_requires_admin_unlock(client, admin_user, admin_assessment):
    login(client, "admin", "adminpass")
    resp = client.get(
        f"/admin/assessments/{admin_assessment.id}/terms",
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert "/admin/unlock" in resp.headers["Location"]


def test_terms_page_loads_empty(client, db, admin_user, admin_assessment):
    login(client, "admin", "adminpass")
    _unlock_admin(client)
    resp = client.get(f"/admin/assessments/{admin_assessment.id}/terms")
    assert resp.status_code == 200
    assert b"Sensitive Terms" in resp.data
    assert b"No sensitive terms" in resp.data


def test_terms_shows_existing(client, db, admin_user, admin_assessment):
    st = SensitiveTerm(
        assessment_id=admin_assessment.id,
        term="Acme Corp",
        replacement_token="[ORG_1]",
        source="auto",
        is_active=True,
    )
    db.session.add(st)
    db.session.commit()

    login(client, "admin", "adminpass")
    _unlock_admin(client)
    resp = client.get(f"/admin/assessments/{admin_assessment.id}/terms")
    assert resp.status_code == 200
    assert b"Acme Corp" in resp.data
    assert b"[ORG_1]" in resp.data


def test_add_term(client, db, admin_user, admin_assessment):
    login(client, "admin", "adminpass")
    _unlock_admin(client)
    resp = client.post(
        f"/admin/assessments/{admin_assessment.id}/terms",
        data={"action": "add", "term": "db01.internal"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"Term added" in resp.data

    st = SensitiveTerm.query.filter_by(
        assessment_id=admin_assessment.id, source="user_added"
    ).first()
    assert st is not None
    assert st.term == "db01.internal"
    assert st.replacement_token == "[CUSTOM_1]"
    assert st.is_active is True


def test_add_term_token_increments(client, db, admin_user, admin_assessment):
    login(client, "admin", "adminpass")
    _unlock_admin(client)
    client.post(
        f"/admin/assessments/{admin_assessment.id}/terms",
        data={"action": "add", "term": "first-term"},
        follow_redirects=True,
    )
    _unlock_admin(client)  # re-unlock in case session refreshed
    client.post(
        f"/admin/assessments/{admin_assessment.id}/terms",
        data={"action": "add", "term": "second-term"},
        follow_redirects=True,
    )
    terms = SensitiveTerm.query.filter_by(
        assessment_id=admin_assessment.id, source="user_added"
    ).order_by(SensitiveTerm.replacement_token).all()
    assert len(terms) == 2
    tokens = {t.replacement_token for t in terms}
    assert "[CUSTOM_1]" in tokens
    assert "[CUSTOM_2]" in tokens


def test_add_empty_term_rejected(client, db, admin_user, admin_assessment):
    login(client, "admin", "adminpass")
    _unlock_admin(client)
    resp = client.post(
        f"/admin/assessments/{admin_assessment.id}/terms",
        data={"action": "add", "term": "   "},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"cannot be empty" in resp.data
    assert SensitiveTerm.query.filter_by(assessment_id=admin_assessment.id).count() == 0


def test_add_term_sanitizes_html(client, db, admin_user, admin_assessment):
    login(client, "admin", "adminpass")
    _unlock_admin(client)
    client.post(
        f"/admin/assessments/{admin_assessment.id}/terms",
        data={"action": "add", "term": "<script>alert(1)</script>hostname"},
        follow_redirects=True,
    )
    st = SensitiveTerm.query.filter_by(assessment_id=admin_assessment.id).first()
    assert st is not None
    assert "<script>" not in st.term
    assert "hostname" in st.term


def test_deactivate_term(client, db, admin_user, admin_assessment):
    st = SensitiveTerm(
        assessment_id=admin_assessment.id,
        term="OldCodename",
        replacement_token="[CUSTOM_1]",
        source="user_added",
        is_active=True,
    )
    db.session.add(st)
    db.session.commit()

    login(client, "admin", "adminpass")
    _unlock_admin(client)
    resp = client.post(
        f"/admin/assessments/{admin_assessment.id}/terms",
        data={"action": "deactivate", "term_id": st.id},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"deactivated" in resp.data
    db.session.refresh(st)
    assert st.is_active is False


def test_deactivate_logs_audit(client, db, admin_user, admin_assessment):
    st = SensitiveTerm(
        assessment_id=admin_assessment.id,
        term="SubsidiaryName",
        replacement_token="[CUSTOM_1]",
        source="user_added",
        is_active=True,
    )
    db.session.add(st)
    db.session.commit()

    login(client, "admin", "adminpass")
    _unlock_admin(client)
    client.post(
        f"/admin/assessments/{admin_assessment.id}/terms",
        data={"action": "deactivate", "term_id": st.id},
        follow_redirects=True,
    )
    log = AuditLog.query.filter_by(
        assessment_id=admin_assessment.id, action="deactivate_sensitive_term"
    ).first()
    assert log is not None
    assert log.before_value == "SubsidiaryName"


def test_deactivate_wrong_assessment_rejected(client, db, admin_user, admin_assessment):
    other = Assessment(customer_org="Other Org", framework="dod_zt", variant="zt_only")
    db.session.add(other)
    db.session.flush()
    st = SensitiveTerm(
        assessment_id=other.id,
        term="Secret",
        replacement_token="[CUSTOM_1]",
        source="user_added",
        is_active=True,
    )
    db.session.add(st)
    db.session.commit()

    login(client, "admin", "adminpass")
    _unlock_admin(client)
    resp = client.post(
        f"/admin/assessments/{admin_assessment.id}/terms",
        data={"action": "deactivate", "term_id": st.id},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"not found" in resp.data.lower()
    db.session.refresh(st)
    assert st.is_active is True  # unchanged


def test_add_term_creates_audit_log(client, db, admin_user, admin_assessment):
    login(client, "admin", "adminpass")
    _unlock_admin(client)
    client.post(
        f"/admin/assessments/{admin_assessment.id}/terms",
        data={"action": "add", "term": "critical-server"},
        follow_redirects=True,
    )
    log = AuditLog.query.filter_by(
        assessment_id=admin_assessment.id, action="add_sensitive_term"
    ).first()
    assert log is not None
    assert log.after_value == "critical-server"


def test_terms_404_on_missing(client, db, admin_user):
    login(client, "admin", "adminpass")
    _unlock_admin(client)
    resp = client.get("/admin/assessments/nonexistent-id/terms")
    assert resp.status_code == 404
