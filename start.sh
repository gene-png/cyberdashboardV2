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
  "$PYTHON" setup_env.py || exit 1
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
