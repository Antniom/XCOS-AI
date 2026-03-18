@echo off
setlocal EnableDelayedExpansion
title XcosGen

:: ── Locate Python ─────────────────────────────────────────────────────────
where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found in PATH. Install Python 3.8+ from python.org.
    pause & exit /b 1
)

:: ── Create / reuse venv ────────────────────────────────────────────────────
set VENV=.venv
if not exist "%VENV%\Scripts\activate.bat" (
    echo [INFO] Creating virtual environment...
    python -m venv "%VENV%"
)

call "%VENV%\Scripts\activate.bat"

:: ── Install / upgrade dependencies ────────────────────────────────────────
echo [INFO] Checking dependencies...
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -r requirements.txt

:: ── Launch app ────────────────────────────────────────────────────────────
echo [INFO] Starting XcosGen...
python main.py

endlocal
