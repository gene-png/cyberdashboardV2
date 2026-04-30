"""
SharePoint integration via Microsoft Graph API.

Uses OAuth2 client-credentials flow (service principal) to authenticate,
then uploads files and creates folders in a SharePoint document library.

All methods are no-ops (log a warning) when credentials are not configured,
so the app runs fully without SharePoint in dev/test.
"""
import csv
import io
import json
import logging
import time
from datetime import datetime, timezone
from typing import Optional

import requests

logger = logging.getLogger(__name__)

_TOKEN_URL = "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
_GRAPH_BASE = "https://graph.microsoft.com/v1.0"

# Token cache — one token per app instance, refreshed when expired
_token_cache: dict = {}


class SharePointClient:
    """
    Thin wrapper around the Microsoft Graph API for file operations.

    Instantiate with the four credentials, then call upload_file / ensure_folder.
    Raises SharePointError on API failures.
    """

    def __init__(self, tenant_id: str, client_id: str, client_secret: str, site_id: str, drive_id: str):
        self.tenant_id = tenant_id
        self.client_id = client_id
        self.client_secret = client_secret
        self.site_id = site_id
        self.drive_id = drive_id
        self._token: Optional[str] = None
        self._token_expiry: float = 0.0

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    def _get_token(self) -> str:
        now = time.time()
        if self._token and now < self._token_expiry - 60:
            return self._token

        url = _TOKEN_URL.format(tenant_id=self.tenant_id)
        resp = requests.post(
            url,
            data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "scope": "https://graph.microsoft.com/.default",
            },
            timeout=15,
        )
        if not resp.ok:
            raise SharePointError(f"Token request failed: {resp.status_code} {resp.text}")

        data = resp.json()
        self._token = data["access_token"]
        self._token_expiry = now + data.get("expires_in", 3600)
        return self._token

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._get_token()}"}

    # ------------------------------------------------------------------
    # Folder operations
    # ------------------------------------------------------------------

    def ensure_folder(self, path: str) -> None:
        """
        Create *path* and all intermediate folders in the drive root.

        Example path: "ZT Assessments/Acme_2026-04-29/outputs"
        Idempotent — safe to call even if the folder already exists.
        """
        parts = [p for p in path.split("/") if p]
        current_path = ""
        for part in parts:
            current_path = f"{current_path}/{part}" if current_path else part
            self._create_folder_if_missing(current_path)

    def _create_folder_if_missing(self, path: str) -> None:
        url = f"{_GRAPH_BASE}/sites/{self.site_id}/drives/{self.drive_id}/root:/{path}"
        check = requests.get(url, headers=self._headers(), timeout=10)
        if check.status_code == 200:
            return  # already exists

        # Create it
        parent_path = "/".join(path.split("/")[:-1])
        folder_name = path.split("/")[-1]
        if parent_path:
            create_url = f"{_GRAPH_BASE}/sites/{self.site_id}/drives/{self.drive_id}/root:/{parent_path}:/children"
        else:
            create_url = f"{_GRAPH_BASE}/sites/{self.site_id}/drives/{self.drive_id}/root/children"

        payload = {"name": folder_name, "folder": {}, "@microsoft.graph.conflictBehavior": "replace"}
        resp = requests.post(create_url, json=payload, headers=self._headers(), timeout=15)
        if not resp.ok and resp.status_code != 409:
            raise SharePointError(f"Folder create failed ({path}): {resp.status_code} {resp.text}")

    # ------------------------------------------------------------------
    # File upload
    # ------------------------------------------------------------------

    def upload_file(self, remote_path: str, content: bytes, content_type: str = "application/octet-stream") -> str:
        """
        Upload *content* to *remote_path* in the drive.

        Returns the item URL. Uses simple upload (suitable for files < 4 MB).
        For larger files the Graph API requires a resumable upload session —
        not needed here as Excel reports and DB backups stay well under 4 MB
        in normal use.
        """
        url = (
            f"{_GRAPH_BASE}/sites/{self.site_id}/drives/{self.drive_id}"
            f"/root:/{remote_path}:/content"
        )
        headers = {**self._headers(), "Content-Type": content_type}
        resp = requests.put(url, data=content, headers=headers, timeout=60)
        if not resp.ok:
            raise SharePointError(f"Upload failed ({remote_path}): {resp.status_code} {resp.text}")
        item = resp.json()
        return item.get("webUrl", "")


class SharePointError(Exception):
    pass


# ---------------------------------------------------------------------------
# High-level operations used by the finalize route
# ---------------------------------------------------------------------------

def _build_readme(org_name: str, assessment_id: str, finalized_at: datetime) -> bytes:
    date_str = finalized_at.strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "Zero Trust Maturity Assessment — Output Package",
        "=" * 48,
        f"Organization : {org_name}",
        f"Assessment ID: {assessment_id}",
        f"Finalized    : {date_str}",
        "",
        "Folder structure:",
        "  inputs/responses_snapshot.json  — raw pillar responses at finalization",
        "  outputs/customer_report.xlsx    — customer-facing gap analysis & recommendations",
        "  outputs/consultant_report.xlsx  — full consultant workbook with scoring detail",
        "  audit/ai_call_log.csv           — log of all Anthropic API calls",
        "  audit/audit_log.csv             — full user-action audit trail",
        "",
        "Generated by the Zero Trust Maturity Assessment Dashboard.",
    ]
    return "\n".join(lines).encode("utf-8")


def upload_assessment_outputs(
    client: SharePointClient,
    assessment_id: str,
    org_name: str,
    finalized_at: datetime,
    customer_xlsx: bytes,
    consultant_xlsx: bytes,
    responses_json: str,
    ai_call_log_rows: list[dict],
    audit_log_rows: list[dict],
) -> dict[str, str]:
    """
    Upload all finalization artifacts to SharePoint.

    Returns a dict of remote_path → webUrl for each uploaded file.
    """
    date_str = finalized_at.strftime("%Y-%m-%d")
    safe_org = _safe_folder_name(org_name)
    base = f"ZT Assessments/{safe_org}_{date_str}"

    # Ensure folder tree
    for sub in ("inputs", "outputs", "audit"):
        client.ensure_folder(f"{base}/{sub}")

    urls: dict[str, str] = {}

    # README
    urls["readme"] = client.upload_file(
        f"{base}/README.txt",
        _build_readme(org_name, assessment_id, finalized_at),
        "text/plain",
    )

    # Inputs
    urls["responses_snapshot"] = client.upload_file(
        f"{base}/inputs/responses_snapshot.json",
        responses_json.encode("utf-8"),
        "application/json",
    )

    # Outputs
    urls["customer_report"] = client.upload_file(
        f"{base}/outputs/customer_report.xlsx",
        customer_xlsx,
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    urls["consultant_report"] = client.upload_file(
        f"{base}/outputs/consultant_report.xlsx",
        consultant_xlsx,
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    # Audit CSVs
    urls["ai_call_log"] = client.upload_file(
        f"{base}/audit/ai_call_log.csv",
        _rows_to_csv(ai_call_log_rows).encode("utf-8"),
        "text/csv",
    )
    urls["audit_log"] = client.upload_file(
        f"{base}/audit/audit_log.csv",
        _rows_to_csv(audit_log_rows).encode("utf-8"),
        "text/csv",
    )

    return urls


def backup_database(client: SharePointClient, db_bytes: bytes) -> str:
    """Upload a DB snapshot to /Backups/{date}/assessments.db. Returns webUrl."""
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    client.ensure_folder(f"Backups/{date_str}")
    return client.upload_file(
        f"Backups/{date_str}/assessments.db",
        db_bytes,
        "application/octet-stream",
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_folder_name(name: str) -> str:
    """Replace characters that are invalid in SharePoint folder names."""
    import re
    return re.sub(r'[\\/*?:<>"|#%]', "_", name).strip()[:64]


def _rows_to_csv(rows: list[dict]) -> str:
    if not rows:
        return ""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue()


def get_client_from_config(config: dict) -> Optional[SharePointClient]:
    """
    Build a SharePointClient from Flask app config.

    Returns None (and logs a warning) if any credential is missing,
    so the rest of the app degrades gracefully.
    """
    required = ("AZURE_TENANT_ID", "AZURE_CLIENT_ID", "AZURE_CLIENT_SECRET",
                 "SHAREPOINT_SITE_ID", "SHAREPOINT_DRIVE_ID")
    if not all(config.get(k) for k in required):
        logger.warning(
            "SharePoint credentials not fully configured — file upload skipped. "
            "Set %s in environment.", ", ".join(required)
        )
        return None
    return SharePointClient(
        tenant_id=config["AZURE_TENANT_ID"],
        client_id=config["AZURE_CLIENT_ID"],
        client_secret=config["AZURE_CLIENT_SECRET"],
        site_id=config["SHAREPOINT_SITE_ID"],
        drive_id=config["SHAREPOINT_DRIVE_ID"],
    )
