import os
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
REPO_ROOT = os.path.abspath(os.path.join(BASE_DIR, ".."))


class Config:
    SECRET_KEY = os.environ.get("FLASK_SECRET_KEY", "dev-secret-change-in-production")
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", f"sqlite:///{os.path.join(REPO_ROOT, 'instance', 'assessments.db')}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = 3600

    # Session cookie hardening (spec §11)
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"

    ADMIN_PASSWORD_HASH = os.environ.get("ADMIN_PASSWORD_HASH", "")
    ADMIN_SESSION_TIMEOUT = 15 * 60  # 15 minutes

    ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
    ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")

    AZURE_TENANT_ID = os.environ.get("AZURE_TENANT_ID", "")
    AZURE_CLIENT_ID = os.environ.get("AZURE_CLIENT_ID", "")
    AZURE_CLIENT_SECRET = os.environ.get("AZURE_CLIENT_SECRET", "")
    SHAREPOINT_SITE_ID = os.environ.get("SHAREPOINT_SITE_ID", "")
    SHAREPOINT_DRIVE_ID = os.environ.get("SHAREPOINT_DRIVE_ID", "")

    FRAMEWORKS_DIR = os.path.join(REPO_ROOT, "data", "frameworks")

    # Set to True to force HTTP → HTTPS redirect (via X-Forwarded-Proto header)
    FORCE_HTTPS = os.environ.get("FORCE_HTTPS", "false").lower() == "true"

    # Tool-to-activity mapping analysis thresholds
    REDUNDANCY_THRESHOLD = int(os.environ.get("REDUNDANCY_THRESHOLD", "3"))
    TOOL_MIN_ACTIVITIES = int(os.environ.get("TOOL_MIN_ACTIVITIES", "2"))

    # Model used for tool-activity mapping suggestions (separate from gap-finding model)
    MAPPING_MODEL = os.environ.get("MAPPING_MODEL", os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6"))

    # ATT&CK coverage report model (defaults to ANTHROPIC_MODEL)
    ATTACK_MODEL = os.environ.get("ATTACK_MODEL", os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6"))

    # Directory where generated ATT&CK coverage Excel reports are stored
    # Defaults to instance/reports/ (gitignored, not served as static)
    REPORTS_DIR = os.environ.get("REPORTS_DIR", os.path.join(REPO_ROOT, "instance", "reports"))


class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False
    SECRET_KEY = "test-secret"
    RATELIMIT_ENABLED = False
    SESSION_COOKIE_SECURE = False  # allow http in tests
    FORCE_HTTPS = False
    import tempfile
    REPORTS_DIR = os.path.join(tempfile.gettempdir(), "zt_test_reports")
