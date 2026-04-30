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
    %PYTHON% setup_env.py
    if errorlevel 1 ( pause & exit /b 1 )
    echo.
    echo   Login at http://localhost:%PORT% with username: admin
    echo.

REM ── 5. Instance directory ─────────────────────────────────────────────────────
if not exist "instance" mkdir instance

REM ── 6. Launch ─────────────────────────────────────────────────────────────────
echo.
echo   Starting on http://localhost:%PORT%
echo   Press Ctrl+C to stop.
echo.

flask --app app run --host=0.0.0.0 --port=%PORT%
pause
