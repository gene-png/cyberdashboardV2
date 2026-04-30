#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Zero Trust Maturity Assessment Dashboard — Local Quick Start
# Runs on macOS and Linux. For Windows use start.bat instead.
# ─────────────────────────────────────────────────────────────────────────────
set -e

PYTHON="${PYTHON:-python3}"
PORT="${PORT:-5000}"

# ── Helpers ───────────────────────────────────────────────────────────────────
bold()  { printf '\033[1m%s\033[0m\n' "$*"; }
info()  { printf '  \033[36m→\033[0m %s\n' "$*"; }
ok()    { printf '  \033[32m✓\033[0m %s\n' "$*"; }
err()   { printf '\033[31mError:\033[0m %s\n' "$*" >&2; exit 1; }
hr()    { printf '\033[90m%s\033[0m\n' "────────────────────────────────────────────────"; }

# ── 1. Python version check ───────────────────────────────────────────────────
command -v "$PYTHON" &>/dev/null || err "Python 3 not found. Install Python 3.11+ from https://python.org"

PY_VER=$("$PYTHON" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PY_MAJ=$(echo "$PY_VER" | cut -d. -f1)
PY_MIN=$(echo "$PY_VER" | cut -d. -f2)
{ [ "$PY_MAJ" -gt 3 ] || { [ "$PY_MAJ" -eq 3 ] && [ "$PY_MIN" -ge 11 ]; }; } \
  || err "Python 3.11+ required (found $PY_VER). Download from https://python.org"
ok "Python $PY_VER"

# ── 2. Virtual environment ────────────────────────────────────────────────────
if [ ! -d ".venv" ]; then
  info "Creating virtual environment..."
  "$PYTHON" -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
ok "Virtual environment active"

# ── 3. Install / update dependencies ─────────────────────────────────────────
info "Installing dependencies (this may take a minute on first run)..."
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt
ok "Dependencies ready"

# ── 4. First-time configuration ───────────────────────────────────────────────
if [ ! -f ".env" ]; then
  echo ""
  hr
  bold "  First-time setup"
  hr
  echo ""
  echo "  You only need to do this once."
  echo "  A .env file will be created in this folder."
  echo ""

  # Admin password
  bold "  Admin password"
  echo "  Used to unlock admin features in the dashboard."
  echo "  Minimum 12 characters."
  echo ""
  while true; do
    read -r -s -p "  Password: " ADMIN_PASS; echo ""
    [ "${#ADMIN_PASS}" -ge 12 ] && break
    echo "  Please choose at least 12 characters."
  done
  read -r -s -p "  Confirm:  " ADMIN_PASS2; echo ""
  [ "$ADMIN_PASS" = "$ADMIN_PASS2" ] || err "Passwords do not match."

  echo ""
  bold "  Anthropic API key (optional)"
  echo "  Required for AI gap findings and ATT&CK coverage reports."
  echo "  Get one at https://console.anthropic.com"
  echo "  Press Enter to skip — you can add it to .env later."
  echo ""
  read -r -p "  API key: " ANTHROPIC_KEY
  echo ""

  # Write .env using Python to safely handle special chars in the hash
  "$PYTHON" - "$ADMIN_PASS" "$ANTHROPIC_KEY" <<'PYEOF'
import sys, secrets
from werkzeug.security import generate_password_hash

password  = sys.argv[1]
api_key   = sys.argv[2]
secret    = secrets.token_hex(32)
pw_hash   = generate_password_hash(password)

with open(".env", "w") as f:
    f.write(f"FLASK_SECRET_KEY={secret}\n")
    f.write(f"ADMIN_PASSWORD_HASH={pw_hash}\n")
    f.write(f"ANTHROPIC_API_KEY={api_key}\n")
    f.write("DATABASE_URL=sqlite:///instance/assessments.db\n")
    f.write("ANTHROPIC_MODEL=claude-sonnet-4-6\n")
    f.write("FORCE_HTTPS=false\n")

print(f"  Saved to .env  (secret_key={secret[:8]}...)")
PYEOF

  echo ""
  echo "  To enable SharePoint upload on finalization, add these to .env:"
  echo "    AZURE_TENANT_ID, AZURE_CLIENT_ID, AZURE_CLIENT_SECRET"
  echo "    SHAREPOINT_SITE_ID, SHAREPOINT_DRIVE_ID"
  echo "  See docs/guides/Setup and SharePoint Integration Guide.docx for details."
  hr
  echo ""
fi

# ── 5. Ensure instance directory exists ───────────────────────────────────────
mkdir -p instance

# ── 6. Launch ─────────────────────────────────────────────────────────────────
echo ""
bold "  Zero Trust Assessment Dashboard"
info "Listening on http://localhost:${PORT}"
info "Press Ctrl+C to stop"
echo ""

flask --app app run --host=0.0.0.0 --port="${PORT}"
