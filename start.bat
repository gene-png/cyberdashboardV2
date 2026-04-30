@echo off
setlocal enabledelayedexpansion
REM ─────────────────────────────────────────────────────────────────────────────
REM Zero Trust Maturity Assessment Dashboard — Windows Quick Start
REM Run this from the repo root: start.bat
REM ─────────────────────────────────────────────────────────────────────────────

set PYTHON=python
set PORT=5000

echo.
echo Zero Trust Maturity Assessment Dashboard
echo ========================================
echo.

REM ── 1. Python check ──────────────────────────────────────────────────────────
where %PYTHON% >nul 2>&1
if errorlevel 1 (
    echo Error: Python not found. Install Python 3.11+ from https://python.org
    pause & exit /b 1
)
for /f "tokens=2 delims= " %%v in ('%PYTHON% --version 2^>^&1') do set PY_VER=%%v
echo   [OK] Python %PY_VER%

REM ── 2. Virtual environment ────────────────────────────────────────────────────
if not exist ".venv" (
    echo   Creating virtual environment...
    %PYTHON% -m venv .venv
)
call .venv\Scripts\activate.bat
echo   [OK] Virtual environment active

REM ── 3. Install dependencies ───────────────────────────────────────────────────
echo   Installing dependencies (may take a minute on first run)...
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt
echo   [OK] Dependencies ready

REM ── 4. First-time configuration ───────────────────────────────────────────────
if not exist ".env" (
    echo.
    echo ────────────────────────────────────────────────
    echo   First-time setup
    echo ────────────────────────────────────────────────
    echo.
    echo   You only need to do this once.
    echo.

    echo   Admin password (minimum 12 characters):
    set /p ADMIN_PASS="  Password: "
    echo.

    echo   Anthropic API key (optional - press Enter to skip):
    echo   Get one at https://console.anthropic.com
    set /p ANTHROPIC_KEY="  API key: "
    echo.

    REM Write .env using Python (handles bcrypt hash special chars safely)
    %PYTHON% -c "
import sys, secrets
from werkzeug.security import generate_password_hash

password = sys.argv[1]
api_key  = sys.argv[2]
secret   = secrets.token_hex(32)
pw_hash  = generate_password_hash(password)

with open('.env', 'w') as f:
    f.write(f'FLASK_SECRET_KEY={secret}\n')
    f.write(f'ADMIN_PASSWORD_HASH={pw_hash}\n')
    f.write(f'ANTHROPIC_API_KEY={api_key}\n')
    f.write('DATABASE_URL=sqlite:///instance/assessments.db\n')
    f.write('ANTHROPIC_MODEL=claude-sonnet-4-6\n')
    f.write('FORCE_HTTPS=false\n')

print(f'  [OK] Saved to .env (key={secret[:8]}...)')
" "!ADMIN_PASS!" "!ANTHROPIC_KEY!"

    echo.
    echo   To enable SharePoint, add these to .env:
    echo     AZURE_TENANT_ID, AZURE_CLIENT_ID, AZURE_CLIENT_SECRET
    echo     SHAREPOINT_SITE_ID, SHAREPOINT_DRIVE_ID
    echo.
    echo ────────────────────────────────────────────────
)

REM ── 5. Instance directory ─────────────────────────────────────────────────────
if not exist "instance" mkdir instance

REM ── 6. Launch ─────────────────────────────────────────────────────────────────
echo.
echo   Starting on http://localhost:%PORT%
echo   Press Ctrl+C to stop.
echo.

flask --app app run --host=0.0.0.0 --port=%PORT%
pause
