"""Tests for the SharePoint service — all HTTP calls mocked."""
import pytest
from unittest.mock import patch, MagicMock
from app.services.sharepoint_service import (
    SharePointClient,
    SharePointError,
    get_client_from_config,
    upload_assessment_outputs,
    backup_database,
    _safe_folder_name,
    _rows_to_csv,
)
from datetime import datetime, timezone


MOCK_CONFIG = {
    "AZURE_TENANT_ID": "tenant-123",
    "AZURE_CLIENT_ID": "client-456",
    "AZURE_CLIENT_SECRET": "secret-789",
    "SHAREPOINT_SITE_ID": "site-abc",
    "SHAREPOINT_DRIVE_ID": "drive-def",
}


# ---- get_client_from_config ----

def test_get_client_returns_none_when_missing_creds():
    client = get_client_from_config({})
    assert client is None


def test_get_client_returns_none_when_partial_creds():
    config = {"AZURE_TENANT_ID": "t", "AZURE_CLIENT_ID": "c"}
    assert get_client_from_config(config) is None


def test_get_client_returns_client_when_all_creds():
    client = get_client_from_config(MOCK_CONFIG)
    assert isinstance(client, SharePointClient)
    assert client.site_id == "site-abc"


# ---- Token acquisition ----

def test_get_token_success():
    client = get_client_from_config(MOCK_CONFIG)

    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.json.return_value = {"access_token": "tok123", "expires_in": 3600}

    with patch("requests.post", return_value=mock_resp):
        token = client._get_token()
    assert token == "tok123"


def test_get_token_failure_raises():
    client = get_client_from_config(MOCK_CONFIG)
    mock_resp = MagicMock()
    mock_resp.ok = False
    mock_resp.status_code = 401
    mock_resp.text = "Unauthorized"

    with patch("requests.post", return_value=mock_resp):
        with pytest.raises(SharePointError, match="Token request failed"):
            client._get_token()


def test_get_token_cached():
    client = get_client_from_config(MOCK_CONFIG)
    client._token = "cached-token"
    client._token_expiry = 9999999999.0  # far future

    with patch("requests.post") as mock_post:
        token = client._get_token()

    mock_post.assert_not_called()
    assert token == "cached-token"


# ---- upload_file ----

def _client_with_token(token="test-token"):
    client = get_client_from_config(MOCK_CONFIG)
    client._token = token
    client._token_expiry = 9999999999.0
    return client


def test_upload_file_success():
    client = _client_with_token()
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.json.return_value = {"webUrl": "https://sharepoint/file.xlsx"}

    with patch("requests.put", return_value=mock_resp):
        url = client.upload_file("path/to/file.xlsx", b"data", "application/octet-stream")

    assert url == "https://sharepoint/file.xlsx"


def test_upload_file_failure_raises():
    client = _client_with_token()
    mock_resp = MagicMock()
    mock_resp.ok = False
    mock_resp.status_code = 403
    mock_resp.text = "Forbidden"

    with patch("requests.put", return_value=mock_resp):
        with pytest.raises(SharePointError, match="Upload failed"):
            client.upload_file("path/file.xlsx", b"data")


# ---- ensure_folder ----

def test_ensure_folder_creates_missing():
    client = _client_with_token()

    # GET returns 404 (not found), POST creates it
    mock_not_found = MagicMock(status_code=404)
    mock_created = MagicMock()
    mock_created.ok = True

    with patch("requests.get", return_value=mock_not_found), \
         patch("requests.post", return_value=mock_created) as mock_post:
        client.ensure_folder("ZT Assessments/TestOrg_2026-04-29/outputs")

    assert mock_post.call_count >= 1  # at least one folder created


def test_ensure_folder_skips_existing():
    client = _client_with_token()
    mock_found = MagicMock(status_code=200)

    with patch("requests.get", return_value=mock_found), \
         patch("requests.post") as mock_post:
        client.ensure_folder("ZT Assessments/existing")

    mock_post.assert_not_called()


# ---- upload_assessment_outputs ----

def test_upload_assessment_outputs_calls_upload_six_times():
    client = _client_with_token()

    with patch.object(client, "ensure_folder"), \
         patch.object(client, "upload_file", return_value="https://sp/file") as mock_upload:
        result = upload_assessment_outputs(
            client=client,
            assessment_id="a1",
            org_name="Acme",
            finalized_at=datetime.now(timezone.utc),
            customer_xlsx=b"cust",
            consultant_xlsx=b"cons",
            responses_json='{"data": 1}',
            ai_call_log_rows=[{"col": "val"}],
            audit_log_rows=[{"col": "val"}],
        )

    # 6 uploads: README, snapshot, customer xlsx, consultant xlsx, ai_call_log csv, audit_log csv
    assert mock_upload.call_count == 6
    assert "customer_report" in result
    assert "consultant_report" in result
    assert "readme" in result


# ---- backup_database ----

def test_backup_database():
    client = _client_with_token()

    with patch.object(client, "ensure_folder"), \
         patch.object(client, "upload_file", return_value="https://sp/backup") as mock_upload:
        url = backup_database(client, b"dbdata")

    assert url == "https://sp/backup"
    # Path should be under Backups/{date}/
    call_path = mock_upload.call_args[0][0]
    assert call_path.startswith("Backups/")
    assert "assessments.db" in call_path


# ---- Helper functions ----

def test_safe_folder_name_strips_special():
    assert _safe_folder_name("Acme / Corp*") == "Acme _ Corp_"


def test_safe_folder_name_truncates():
    long_name = "A" * 100
    assert len(_safe_folder_name(long_name)) <= 64


def test_rows_to_csv_empty():
    assert _rows_to_csv([]) == ""


def test_rows_to_csv_generates_header():
    rows = [{"col1": "a", "col2": "b"}]
    csv_str = _rows_to_csv(rows)
    assert "col1" in csv_str
    assert "col2" in csv_str
    assert "a" in csv_str
