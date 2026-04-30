"""Tests for the ATT&CK coverage report routes."""
import json
import os
import pytest
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

from tests.conftest import login
from app.models import Assessment, ToolInventory
from app.models.mitre_technique import MitreTechnique
from app.models.attack_coverage_run import AttackCoverageRun
from app.models.coverage_report import CoverageReport
from app.models.tool_activity_mapping import ToolActivityMapping
from app.extensions import db as ext_db


def _unlock_admin(client):
    with client.session_transaction() as sess:
        sess["admin_unlocked_at"] = datetime.now(timezone.utc).isoformat()


def _make_active_tool(db, assessment_id, name="Splunk"):
    tool = ToolInventory(
        assessment_id=assessment_id,
        name=name,
        vendor="Vendor",
        category="SIEM",
        mapping_status="active",
    )
    db.session.add(tool)
    db.session.flush()
    # Add a confirmed mapping
    mapping = ToolActivityMapping(
        tool_id=tool.id,
        activity_id="act.1.1",
        source="admin_confirmed",
    )
    db.session.add(mapping)
    db.session.commit()
    return tool


def _seed_techniques(db, count=3):
    techniques = []
    for i in range(1, count + 1):
        t = MitreTechnique(
            technique_id=f"T100{i}",
            sub_technique_id=None,
            name=f"Technique {i}",
            tactic="Initial Access",
            description=f"Desc {i}",
            url=f"https://attack.mitre.org/techniques/T100{i}",
            is_sub_technique=False,
        )
        db.session.add(t)
        techniques.append(t)
    db.session.commit()
    return techniques


# ---- GET /admin/assessments/<id>/attack-coverage ----

def test_attack_coverage_page_requires_admin(client, db, sample_assessment):
    login(client, "testcustomer", "custpass")
    resp = client.get(
        f"/admin/assessments/{sample_assessment.id}/attack-coverage",
        follow_redirects=False,
    )
    assert resp.status_code == 302


def test_attack_coverage_page_loads(client, db, sample_assessment):
    login(client, "testcustomer", "custpass")
    _unlock_admin(client)
    resp = client.get(f"/admin/assessments/{sample_assessment.id}/attack-coverage")
    assert resp.status_code == 200
    assert b"ATT&CK Coverage Report" in resp.data


def test_attack_coverage_shows_empty_state(client, db, sample_assessment):
    login(client, "testcustomer", "custpass")
    _unlock_admin(client)
    resp = client.get(f"/admin/assessments/{sample_assessment.id}/attack-coverage")
    assert b"No reports generated yet" in resp.data


def test_attack_coverage_shows_technique_db_warning(client, db, sample_assessment):
    login(client, "testcustomer", "custpass")
    _unlock_admin(client)
    # No techniques seeded → should show warning
    resp = client.get(f"/admin/assessments/{sample_assessment.id}/attack-coverage")
    assert b"seed_mitre.py" in resp.data


# ---- POST /admin/assessments/<id>/attack-coverage/generate ----

def test_generate_warns_when_no_techniques(client, db, sample_assessment):
    login(client, "testcustomer", "custpass")
    _unlock_admin(client)
    _make_active_tool(db, sample_assessment.id)
    resp = client.post(
        f"/admin/assessments/{sample_assessment.id}/attack-coverage/generate",
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"seed_mitre.py" in resp.data


def test_generate_warns_when_no_active_tools(client, db, sample_assessment):
    login(client, "testcustomer", "custpass")
    _unlock_admin(client)
    _seed_techniques(db)
    resp = client.post(
        f"/admin/assessments/{sample_assessment.id}/attack-coverage/generate",
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"No tools with finalized mappings" in resp.data


def test_generate_creates_report_record(client, db, sample_assessment, tmp_path):
    login(client, "testcustomer", "custpass")
    _unlock_admin(client)
    tool = _make_active_tool(db, sample_assessment.id)
    techniques = _seed_techniques(db)

    mock_results = [
        {"technique_id": "T1001", "coverage_type": "detect", "confidence": "high", "rationale": "Detects network."}
    ]

    # Patch map_tool_to_techniques and REPORTS_DIR only; let current_app be real
    with patch("app.routes.admin.map_tool_to_techniques", return_value=(mock_results, None)), \
         patch.dict("os.environ", {"REPORTS_DIR": str(tmp_path)}):
        resp = client.post(
            f"/admin/assessments/{sample_assessment.id}/attack-coverage/generate",
            follow_redirects=True,
        )

    assert resp.status_code == 200
    report = CoverageReport.query.filter_by(assessment_id=sample_assessment.id).first()
    assert report is not None
    assert report.tool_count == 1


def test_generate_caches_run_for_tool(client, db, sample_assessment, tmp_path):
    login(client, "testcustomer", "custpass")
    _unlock_admin(client)
    tool = _make_active_tool(db, sample_assessment.id)
    _seed_techniques(db)

    mock_results = [
        {"technique_id": "T1001", "coverage_type": "prevent", "confidence": "medium", "rationale": "Prevents it."}
    ]

    with patch("app.routes.admin.map_tool_to_techniques", return_value=(mock_results, None)), \
         patch.dict("os.environ", {"REPORTS_DIR": str(tmp_path)}):
        client.post(
            f"/admin/assessments/{sample_assessment.id}/attack-coverage/generate",
            follow_redirects=True,
        )

    run = AttackCoverageRun.query.filter_by(
        assessment_id=sample_assessment.id, tool_id=tool.id
    ).first()
    assert run is not None
    payload = json.loads(run.response_payload)
    assert payload[0]["technique_id"] == "T1001"


# ---- Download route ----

def test_download_requires_admin(client, db, sample_assessment):
    login(client, "testcustomer", "custpass")
    resp = client.get(
        f"/admin/assessments/{sample_assessment.id}/attack-coverage/fake-id/download",
        follow_redirects=False,
    )
    assert resp.status_code == 302


def test_download_404_for_unknown_report(client, db, sample_assessment):
    login(client, "testcustomer", "custpass")
    _unlock_admin(client)
    resp = client.get(
        f"/admin/assessments/{sample_assessment.id}/attack-coverage/nonexistent/download",
    )
    assert resp.status_code == 404
