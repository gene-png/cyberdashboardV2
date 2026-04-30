"""End-to-end cycle tests for CISA ZT framework."""
import pytest
from datetime import datetime, timezone
from tests.conftest import login
from app.models import Assessment, Response, GapFinding, AdminScore
from app.extensions import db as ext_db
from app.services.framework_loader import load_framework
from app.services.excel_service import build_customer_excel, build_consultant_excel, _compute_pillar_stats


# ---- Framework loader ----

def test_cisa_framework_loads():
    fw = load_framework("cisa_zt")
    assert "CISA" in fw["name"]
    assert len(fw["pillars"]) == 5
    assert set(fw["maturity_states"]) == {"traditional", "initial", "advanced", "optimal"}


def test_cisa_maturity_order_correct():
    fw = load_framework("cisa_zt")
    order = fw["maturity_order"]
    assert order["traditional"] < order["initial"] < order["advanced"] < order["optimal"]


def test_cisa_all_activities_have_ids():
    fw = load_framework("cisa_zt")
    for pillar in fw["pillars"]:
        for activity in pillar["activities"]:
            assert activity["id"].startswith("cisa_zt.")
            assert activity["name"]


# ---- Assessment creation with CISA framework ----

def test_cisa_assessment_wizard(client, db, admin_user):
    login(client, "admin", "adminpass")
    with client.session_transaction() as sess:
        sess["admin_unlocked_at"] = datetime.now(timezone.utc).isoformat()

    resp = client.post(
        "/assessments/new",
        data={
            "customer_org": "CISA Test Agency",
            "framework": "cisa_zt",
            "variant": "full",
            "username": "cisa_customer",
            "password": "cisapass123",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    a = Assessment.query.filter_by(customer_org="CISA Test Agency").first()
    assert a is not None
    assert a.framework == "cisa_zt"


def test_cisa_pillar_page_loads(client, db):
    from app.models import User
    a = Assessment(customer_org="CISA Agency", framework="cisa_zt", variant="full", status="draft")
    db.session.add(a)
    db.session.flush()
    u = User(username="cisauser", role="customer", assessment_id=a.id)
    u.set_password("pass")
    db.session.add(u)
    db.session.commit()

    login(client, "cisauser", "pass")
    resp = client.get(f"/assessments/{a.id}/pillar/identity")
    assert resp.status_code == 200
    assert b"identity" in resp.data.lower() or b"Identity" in resp.data


# ---- _compute_pillar_stats with CISA framework ----

def test_compute_pillar_stats_cisa(db):
    fw = load_framework("cisa_zt")
    a = Assessment(customer_org="Stats Org", framework="cisa_zt", variant="full", status="in_progress")
    db.session.add(a)
    db.session.flush()

    # Add responses for the identity pillar: traditional → advanced (gap of 2)
    identity_pillar = next(p for p in fw["pillars"] if p["id"] == "identity")
    for activity in identity_pillar["activities"]:
        r = Response(
            assessment_id=a.id,
            pillar="identity",
            activity_id=activity["id"],
            current_state_value="traditional",
            target_state_value="advanced",
        )
        db.session.add(r)
    db.session.commit()

    stats = _compute_pillar_stats(a, fw)
    identity_stat = next(s for s in stats if s["pillar_id"] == "identity")
    assert identity_stat["gap"] > 0
    assert identity_stat["current_score"] < identity_stat["target_score"]
    assert identity_stat["gap_large"] == len(identity_pillar["activities"])
    assert identity_stat["gap_small"] == 0
    assert identity_stat["met"] == 0


def test_compute_pillar_stats_cisa_met(db):
    fw = load_framework("cisa_zt")
    a = Assessment(customer_org="Met Org", framework="cisa_zt", variant="full", status="in_progress")
    db.session.add(a)
    db.session.flush()

    # All activities at target (optimal → optimal)
    identity_pillar = next(p for p in fw["pillars"] if p["id"] == "identity")
    for activity in identity_pillar["activities"]:
        r = Response(
            assessment_id=a.id,
            pillar="identity",
            activity_id=activity["id"],
            current_state_value="optimal",
            target_state_value="optimal",
        )
        db.session.add(r)
    db.session.commit()

    stats = _compute_pillar_stats(a, fw)
    identity_stat = next(s for s in stats if s["pillar_id"] == "identity")
    assert identity_stat["met"] == len(identity_pillar["activities"])
    assert identity_stat["gap_large"] == 0
    assert identity_stat["gap_small"] == 0


# ---- Excel generation with CISA framework ----

def test_build_customer_excel_cisa(db):
    fw = load_framework("cisa_zt")
    a = Assessment(
        customer_org="Excel CISA Org",
        framework="cisa_zt",
        variant="full",
        status="finalized",
        finalized_at=datetime.now(timezone.utc),
    )
    db.session.add(a)
    db.session.flush()

    for pillar in fw["pillars"]:
        for activity in pillar["activities"]:
            r = Response(
                assessment_id=a.id,
                pillar=pillar["id"],
                activity_id=activity["id"],
                current_state_value="initial",
                target_state_value="advanced",
            )
            db.session.add(r)
    db.session.commit()

    xlsx_bytes = build_customer_excel(a)
    assert isinstance(xlsx_bytes, bytes)
    assert len(xlsx_bytes) > 0


def test_build_consultant_excel_cisa(db):
    fw = load_framework("cisa_zt")
    a = Assessment(
        customer_org="Consultant CISA Org",
        framework="cisa_zt",
        variant="full",
        status="finalized",
        finalized_at=datetime.now(timezone.utc),
    )
    db.session.add(a)
    db.session.flush()

    for pillar in fw["pillars"]:
        for activity in pillar["activities"]:
            r = Response(
                assessment_id=a.id,
                pillar=pillar["id"],
                activity_id=activity["id"],
                current_state_value="traditional",
                target_state_value="optimal",
            )
            db.session.add(r)
    db.session.commit()

    xlsx_bytes = build_consultant_excel(a)
    assert isinstance(xlsx_bytes, bytes)
    assert len(xlsx_bytes) > 0


# ---- HTMX auto-save with CISA framework ----

def test_cisa_autosave_response(client, db):
    from app.models import User
    a = Assessment(customer_org="HTMX CISA", framework="cisa_zt", variant="full", status="draft")
    db.session.add(a)
    db.session.flush()
    u = User(username="cisahtmx", role="customer", assessment_id=a.id)
    u.set_password("pass")
    db.session.add(u)
    db.session.commit()

    login(client, "cisahtmx", "pass")
    resp = client.post(
        f"/htmx/assessments/{a.id}/response/cisa_zt.identity.1.1",
        data={"current": "traditional", "target": "advanced", "notes": "Starting from scratch"},
    )
    assert resp.status_code == 200
    assert b"Saved" in resp.data

    saved = Response.query.filter_by(assessment_id=a.id, activity_id="cisa_zt.identity.1.1").first()
    assert saved is not None
    assert saved.current_state_value == "traditional"
    assert saved.target_state_value == "advanced"
