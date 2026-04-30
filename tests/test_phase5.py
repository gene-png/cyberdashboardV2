"""Tests for Phase 5 hardening features."""
import io
import pytest
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock
from tests.conftest import login
from app.models import Assessment, SensitiveTerm
from app.extensions import db as ext_db


# ---- Helpers ----

def _finalize_assessment(db, assessment):
    assessment.status = "finalized"
    assessment.finalized_at = datetime.now(timezone.utc)
    db.session.commit()


# ---- Customer final report download ----

def test_final_report_requires_login(client, sample_assessment):
    _finalize_assessment(ext_db, sample_assessment)
    resp = client.get(
        f"/assessments/{sample_assessment.id}/report",
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_final_report_not_finalized_redirects(client, db, sample_assessment):
    login(client, "testcustomer", "custpass")
    assert sample_assessment.status == "draft"
    resp = client.get(
        f"/assessments/{sample_assessment.id}/report",
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"only available after" in resp.data


def test_final_report_returns_xlsx(client, db, sample_assessment):
    _finalize_assessment(db, sample_assessment)
    login(client, "testcustomer", "custpass")
    resp = client.get(f"/assessments/{sample_assessment.id}/report")
    assert resp.status_code == 200
    assert resp.content_type == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert b"PK" in resp.data  # zip/xlsx magic bytes


def test_final_report_filename_contains_org(client, db, sample_assessment):
    _finalize_assessment(db, sample_assessment)
    login(client, "testcustomer", "custpass")
    resp = client.get(f"/assessments/{sample_assessment.id}/report")
    disposition = resp.headers.get("Content-Disposition", "")
    assert "Test_Org" in disposition or "Test Org" in disposition


def test_final_report_forbidden_for_other_customer(client, db, sample_assessment):
    _finalize_assessment(db, sample_assessment)
    from app.models import User
    other_assessment = Assessment(
        customer_org="Other Org", framework="dod_zt", variant="zt_only"
    )
    db.session.add(other_assessment)
    db.session.flush()
    other_user = User(username="otheruser", role="customer", assessment_id=other_assessment.id)
    other_user.set_password("otherpass")
    db.session.add(other_user)
    db.session.commit()

    login(client, "otheruser", "otherpass")
    resp = client.get(f"/assessments/{sample_assessment.id}/report")
    assert resp.status_code == 403


# ---- Session cookie config ----

def test_session_cookie_httponly(app):
    assert app.config["SESSION_COOKIE_HTTPONLY"] is True


def test_session_cookie_samesite(app):
    assert app.config["SESSION_COOKIE_SAMESITE"] == "Lax"


def test_force_https_disabled_in_testing(app):
    assert app.config.get("FORCE_HTTPS") is False


# ---- HTTPS redirect hook ----

def test_https_redirect_fires_when_enabled():
    from app import create_app
    from app.config import TestingConfig

    class HttpsConfig(TestingConfig):
        FORCE_HTTPS = True

    test_app = create_app(HttpsConfig)
    with test_app.test_client() as c:
        resp = c.get(
            "/login",
            headers={"X-Forwarded-Proto": "http", "Host": "example.com"},
            follow_redirects=False,
        )
    assert resp.status_code == 301
    assert resp.headers["Location"].startswith("https://")


def test_https_redirect_not_fired_for_https():
    from app import create_app
    from app.config import TestingConfig

    class HttpsConfig(TestingConfig):
        FORCE_HTTPS = True

    test_app = create_app(HttpsConfig)
    with test_app.test_client() as c:
        resp = c.get(
            "/login",
            headers={"X-Forwarded-Proto": "https"},
            follow_redirects=False,
        )
    # Should not redirect (login page returns 200)
    assert resp.status_code == 200


# ---- spaCy NER scrub layer ----

def test_ner_scrub_adds_token_for_unknown_org(db, sample_assessment):
    from app.services.scrub_service import scrub

    # Mock the NER model to return a predictable entity
    mock_ent = MagicMock()
    mock_ent.text = "Acme Federal"
    mock_ent.label_ = "ORG"

    mock_doc = MagicMock()
    mock_doc.ents = [mock_ent]

    mock_nlp = MagicMock(return_value=mock_doc)

    with patch("app.services.scrub_service._get_nlp", return_value=mock_nlp), \
         patch("app.services.scrub_service._nlp", mock_nlp), \
         patch("app.services.scrub_service._nlp_loaded", True):
        result = scrub(sample_assessment.id, "We work with Acme Federal on this.")

    assert "Acme Federal" not in result
    assert "[ORG_" in result


def test_ner_scrub_skips_vendor_allowlisted_terms(db, sample_assessment):
    from app.services.scrub_service import scrub

    mock_ent = MagicMock()
    mock_ent.text = "Microsoft"
    mock_ent.label_ = "ORG"

    mock_doc = MagicMock()
    mock_doc.ents = [mock_ent]
    mock_nlp = MagicMock(return_value=mock_doc)

    with patch("app.services.scrub_service._get_nlp", return_value=mock_nlp), \
         patch("app.services.scrub_service._nlp", mock_nlp), \
         patch("app.services.scrub_service._nlp_loaded", True):
        result = scrub(sample_assessment.id, "We use Microsoft Defender.")

    assert "Microsoft" in result


def test_ner_scrub_skips_already_mapped_terms(db, sample_assessment):
    from app.services.scrub_service import scrub, seed_token_map

    seed_token_map(sample_assessment.id, "Test Org", [])

    mock_ent = MagicMock()
    mock_ent.text = "Test Org"
    mock_ent.label_ = "ORG"

    mock_doc = MagicMock()
    mock_doc.ents = [mock_ent]
    mock_nlp = MagicMock(return_value=mock_doc)

    with patch("app.services.scrub_service._get_nlp", return_value=mock_nlp), \
         patch("app.services.scrub_service._nlp", mock_nlp), \
         patch("app.services.scrub_service._nlp_loaded", True):
        result = scrub(sample_assessment.id, "Test Org uses zero trust.")

    # Should be replaced by existing [ORG_1] from Layer 1, not create a duplicate
    token_count = result.count("[ORG_")
    assert token_count == 1


def test_ner_scrub_degrades_gracefully_when_unavailable(db, sample_assessment):
    from app.services.scrub_service import scrub

    with patch("app.services.scrub_service._get_nlp", return_value=None), \
         patch("app.services.scrub_service._nlp", None), \
         patch("app.services.scrub_service._nlp_loaded", True):
        result = scrub(sample_assessment.id, "No scrubbing without NER.")

    # Should not crash; text passes through unchanged by NER
    assert "No scrubbing" in result


def test_ner_scrub_person_entity_uses_person_prefix(db, sample_assessment):
    from app.services.scrub_service import scrub

    mock_ent = MagicMock()
    mock_ent.text = "John Smith"
    mock_ent.label_ = "PERSON"

    mock_doc = MagicMock()
    mock_doc.ents = [mock_ent]
    mock_nlp = MagicMock(return_value=mock_doc)

    with patch("app.services.scrub_service._get_nlp", return_value=mock_nlp), \
         patch("app.services.scrub_service._nlp", mock_nlp), \
         patch("app.services.scrub_service._nlp_loaded", True):
        result = scrub(sample_assessment.id, "Contact John Smith for details.")

    assert "John Smith" not in result
    assert "[PERSON_" in result


def test_ner_new_terms_persisted_to_db(db, sample_assessment):
    from app.services.scrub_service import scrub

    mock_ent = MagicMock()
    mock_ent.text = "Pentagon Agency"
    mock_ent.label_ = "ORG"

    mock_doc = MagicMock()
    mock_doc.ents = [mock_ent]
    mock_nlp = MagicMock(return_value=mock_doc)

    with patch("app.services.scrub_service._get_nlp", return_value=mock_nlp), \
         patch("app.services.scrub_service._nlp", mock_nlp), \
         patch("app.services.scrub_service._nlp_loaded", True):
        scrub(sample_assessment.id, "Pentagon Agency is our customer.")

    term = SensitiveTerm.query.filter_by(
        assessment_id=sample_assessment.id, term="Pentagon Agency"
    ).first()
    assert term is not None
    assert term.source == "auto"


# ---- create_admin.py script ----

def test_create_admin_script_produces_hash():
    import subprocess, sys
    result = subprocess.run(
        [sys.executable, "scripts/create_admin.py", "--password", "TestPassword123"],
        capture_output=True, text=True, cwd="/workspace",
    )
    assert result.returncode == 0
    assert "ADMIN_PASSWORD_HASH=" in result.stdout
    hash_line = [l for l in result.stdout.splitlines() if l.startswith("ADMIN_PASSWORD_HASH=")][0]
    hash_value = hash_line.split("=", 1)[1]
    from werkzeug.security import check_password_hash
    assert check_password_hash(hash_value, "TestPassword123")
