"""Tests for assessment workspace routes."""
import pytest
from tests.conftest import login
from app.models import Assessment, Response, ToolInventory


def test_workspace_redirects_customer(client, sample_assessment):
    login(client, "testcustomer", "custpass")
    resp = client.get(f"/assessments/{sample_assessment.id}")
    assert resp.status_code == 200
    assert b"Assessment Workspace" in resp.data


def test_inventory_page_loads(client, sample_assessment):
    login(client, "testcustomer", "custpass")
    resp = client.get(f"/assessments/{sample_assessment.id}/inventory")
    assert resp.status_code == 200
    assert b"Tool Inventory" in resp.data


def test_add_tool(client, db, sample_assessment):
    login(client, "testcustomer", "custpass")
    resp = client.post(
        f"/assessments/{sample_assessment.id}/inventory",
        data={
            "name": "Splunk",
            "vendor": "Splunk Inc",
            "category": "SIEM",
            "notes": "On-prem deployment",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"Tool added" in resp.data
    tools = ToolInventory.query.filter_by(assessment_id=sample_assessment.id).all()
    assert len(tools) == 1
    assert tools[0].name == "Splunk"


def test_pillar_page_loads(client, sample_assessment):
    login(client, "testcustomer", "custpass")
    resp = client.get(f"/assessments/{sample_assessment.id}/pillar/user")
    assert resp.status_code == 200
    assert b"User" in resp.data


def test_save_pillar_responses(client, db, sample_assessment):
    login(client, "testcustomer", "custpass")
    data = {
        "current_dod_zt.user.1.1": "partial",
        "target_dod_zt.user.1.1": "target",
        "notes_dod_zt.user.1.1": "MFA deployed for most users",
    }
    resp = client.post(
        f"/assessments/{sample_assessment.id}/pillar/user",
        data=data,
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"Responses saved" in resp.data

    saved = Response.query.filter_by(
        assessment_id=sample_assessment.id,
        activity_id="dod_zt.user.1.1",
    ).first()
    assert saved is not None
    assert saved.current_state_value == "partial"
    assert saved.target_state_value == "target"


def test_submit_assessment(client, db, sample_assessment):
    login(client, "testcustomer", "custpass")
    # Flip to in_progress first
    sample_assessment.status = "in_progress"
    db.session.commit()

    resp = client.post(
        f"/assessments/{sample_assessment.id}/submit",
        follow_redirects=True,
    )
    assert resp.status_code == 200

    from app.extensions import db as ext_db
    ext_db.session.refresh(sample_assessment)
    assert sample_assessment.status == "awaiting_review"


def test_customer_cannot_access_other_assessment(client, db, sample_assessment):
    other = Assessment(customer_org="Other Org", framework="dod_zt", variant="zt_only")
    db.session.add(other)
    db.session.commit()

    login(client, "testcustomer", "custpass")
    resp = client.get(f"/assessments/{other.id}")
    assert resp.status_code == 403


def test_submit_page_loads(client, sample_assessment):
    login(client, "testcustomer", "custpass")
    resp = client.get(f"/assessments/{sample_assessment.id}/submit")
    assert resp.status_code == 200
    assert b"Submit" in resp.data
