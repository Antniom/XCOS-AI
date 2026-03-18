@echo off
setlocal EnableDelayedExpansion
title XcosGen — Build Installer

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

:: ── Install dependencies (including PyInstaller) ──────────────────────────
echo [INFO] Installing / updating dependencies...
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -r requirements.txt
python -m pip install --quiet "pyinstaller>=6.0.0"

:: ── Run build pipeline ────────────────────────────────────────────────────
echo.
echo [INFO] Building executable and installer...
echo        (This may take a few minutes on first run)
echo.
python build.py --installer

echo.
if errorlevel 1 (
    echo [ERROR] Build failed. Check the output above.
) else (
    echo [INFO] Done!  Installer is in:  dist\installer\
    echo        Executable is in:        dist\XcosGen\XcosGen.exe
)

pause
endlocal
