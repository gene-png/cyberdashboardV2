#!/usr/bin/env python3
"""
Nightly DB backup — uploads assessments.db to SharePoint /Backups/{date}/.

Retains last 30 days of backups (prunes older folders).

Usage:
    python scripts/backup_db.py

Expects the same environment variables as the Flask app.
Add to cron: 0 2 * * * /path/to/.venv/bin/python /path/to/scripts/backup_db.py
"""
import os
import sys
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Allow imports from the repo root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

RETAIN_DAYS = 30


def main():
    from app.services.sharepoint_service import get_client_from_config, backup_database, SharePointError
    import requests

    config = {
        "AZURE_TENANT_ID": os.environ.get("AZURE_TENANT_ID", ""),
        "AZURE_CLIENT_ID": os.environ.get("AZURE_CLIENT_ID", ""),
        "AZURE_CLIENT_SECRET": os.environ.get("AZURE_CLIENT_SECRET", ""),
        "SHAREPOINT_SITE_ID": os.environ.get("SHAREPOINT_SITE_ID", ""),
        "SHAREPOINT_DRIVE_ID": os.environ.get("SHAREPOINT_DRIVE_ID", ""),
    }

    client = get_client_from_config(config)
    if not client:
        logger.error("SharePoint credentials not configured. Backup skipped.")
        sys.exit(1)

    db_path = os.environ.get("DATABASE_URL", "sqlite:///instance/assessments.db")
    # Strip sqlite:/// prefix
    if db_path.startswith("sqlite:///"):
        db_path = db_path[len("sqlite:///"):]
    if not os.path.isabs(db_path):
        db_path = str(Path(__file__).resolve().parent.parent / db_path)

    if not os.path.exists(db_path):
        logger.error("Database file not found: %s", db_path)
        sys.exit(1)

    db_bytes = Path(db_path).read_bytes()
    logger.info("Uploading DB (%d bytes) to SharePoint...", len(db_bytes))

    try:
        url = backup_database(client, db_bytes)
        logger.info("Backup complete: %s", url)
    except SharePointError as e:
        logger.error("Backup failed: %s", e)
        sys.exit(1)

    # Prune backups older than RETAIN_DAYS
    cutoff = datetime.now(timezone.utc) - timedelta(days=RETAIN_DAYS)
    _prune_old_backups(client, cutoff)


def _prune_old_backups(client, cutoff: datetime) -> None:
    """Delete /Backups/{date} folders older than cutoff date."""
    import requests
    from app.services.sharepoint_service import _GRAPH_BASE

    try:
        headers = client._headers()
        url = f"{_GRAPH_BASE}/sites/{client.site_id}/drives/{client.drive_id}/root:/Backups:/children"
        resp = requests.get(url, headers=headers, timeout=10)
        if not resp.ok:
            logger.warning("Could not list Backups folder: %s", resp.status_code)
            return

        items = resp.json().get("value", [])
        for item in items:
            name = item.get("name", "")
            try:
                folder_date = datetime.strptime(name, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            except ValueError:
                continue
            if folder_date < cutoff:
                item_id = item["id"]
                del_url = f"{_GRAPH_BASE}/sites/{client.site_id}/drives/{client.drive_id}/items/{item_id}"
                del_resp = requests.delete(del_url, headers=headers, timeout=10)
                if del_resp.ok:
                    logger.info("Pruned old backup: %s", name)
                else:
                    logger.warning("Could not prune %s: %s", name, del_resp.status_code)
    except Exception as e:
        logger.warning("Prune step failed (non-fatal): %s", e)


if __name__ == "__main__":
    main()
