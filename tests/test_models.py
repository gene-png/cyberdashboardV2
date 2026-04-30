"""Tests for SQLAlchemy models."""
import pytest
from app.models import Assessment, User, ToolInventory, Response, AdminScore


def test_assessment_create(db):
    a = Assessment(customer_org="Acme", framework="dod_zt", variant="zt_only")
    db.session.add(a)
    db.session.commit()
    assert a.id is not None
    assert a.status == "draft"
    assert a.is_editable_by_customer is True
    assert a.is_finalized is False


def test_assessment_finalize(db):
    a = Assessment(customer_org="Beta", framework="cisa_zt", variant="zt_only")
    db.session.add(a)
    db.session.commit()
    a.status = "finalized"
    db.session.commit()
    assert a.is_finalized is True
    assert a.is_editable_by_customer is False


def test_user_password_hash(db):
    u = User(username="alice", role="customer")
    u.set_password("s3cr3t!")
    db.session.add(u)
    db.session.commit()
    assert u.check_password("s3cr3t!") is True
    assert u.check_password("wrongpassword") is False


def test_tool_inventory(db, sample_assessment):
    tool = ToolInventory(
        assessment_id=sample_assessment.id,
        name="CrowdStrike Falcon",
        vendor="CrowdStrike",
        category="EDR",
    )
    db.session.add(tool)
    db.session.commit()
    assert tool.id is not None
    assert len(sample_assessment.tool_inventory) == 1


def test_response_has_gap(db, sample_assessment):
    # DoD ZT maturity order: not_met=0, partial=1, target=2, advanced=3
    maturity_order = {"not_met": 0, "partial": 1, "target": 2, "advanced": 3}
    resp = Response(
        assessment_id=sample_assessment.id,
        pillar="user",
        activity_id="dod_zt.user.1.1",
        current_state_value="not_met",
        target_state_value="target",
    )
    assert resp.has_gap(maturity_order) is True

    resp_no_gap = Response(
        assessment_id=sample_assessment.id,
        pillar="user",
        activity_id="dod_zt.user.1.2",
        current_state_value="target",
        target_state_value="target",
    )
    assert resp_no_gap.has_gap(maturity_order) is False


def test_admin_score_unique_constraint(db, sample_assessment):
    score1 = AdminScore(assessment_id=sample_assessment.id, pillar="user", current_score=50.0)
    db.session.add(score1)
    db.session.commit()

    score2 = AdminScore(assessment_id=sample_assessment.id, pillar="user", current_score=60.0)
    db.session.add(score2)
    with pytest.raises(Exception):
        db.session.commit()
