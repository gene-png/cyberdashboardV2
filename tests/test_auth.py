"""Tests for authentication routes."""
import pytest
from tests.conftest import login


def test_landing_page_loads(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"Zero Trust" in resp.data


def test_login_page_loads(client):
    resp = client.get("/login")
    assert resp.status_code == 200
    assert b"Sign In" in resp.data


def test_resume_page_loads(client):
    resp = client.get("/resume")
    assert resp.status_code == 200
    assert b"Resume" in resp.data


def test_login_success(client, sample_assessment):
    resp = login(client, "testcustomer", "custpass")
    assert resp.status_code == 200
    # Should redirect to workspace, not stay on login page
    assert b"Sign In" not in resp.data


def test_login_bad_password(client, sample_assessment):
    resp = login(client, "testcustomer", "wrongpassword")
    assert b"Invalid username or password" in resp.data


def test_login_unknown_user(client):
    resp = login(client, "nobody", "nopass")
    assert b"Invalid username or password" in resp.data


def test_logout_redirects_to_landing(client, sample_assessment):
    login(client, "testcustomer", "custpass")
    resp = client.get("/logout", follow_redirects=True)
    assert resp.status_code == 200
    # Landing page content
    assert b"Zero Trust" in resp.data


def test_dashboard_requires_login(client):
    resp = client.get("/dashboard", follow_redirects=True)
    # Redirected to login page
    assert b"Sign In" in resp.data


def test_admin_unlock_page(client, sample_assessment):
    login(client, "testcustomer", "custpass")
    resp = client.get("/admin/unlock")
    assert resp.status_code == 200
    assert b"Admin" in resp.data


def test_start_assessment_page_loads(client):
    resp = client.get("/start")
    assert resp.status_code == 200
    assert b"Start" in resp.data
