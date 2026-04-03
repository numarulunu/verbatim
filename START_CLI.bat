@echo off
cls
cd /d "%~dp0"

REM Determine source folder
set "SOURCE_DIR=%~1"
if "%SOURCE_DIR%"=="" set "SOURCE_DIR=%~dp0Material"
if not exist "%SOURCE_DIR%" (
    echo No input folder found.
    echo Expected folder: %SOURCE_DIR%
    echo.
    echo Create the folder or drag a source folder onto START.bat.
    pause
    exit /b
)

REM Select Python environment
set "VENV_DIR=backend\.venv"

if not exist "%VENV_DIR%\Scripts\python.exe" (
    echo Python virtual environment not found at %VENV_DIR%\
    echo Create it with: python -m venv backend\.venv
    pause
    exit /b
)

set "VENV_PY=%VENV_DIR%\Scripts\python.exe"

REM Ensure dependencies are installed / updated
REM Run manual dependency install script (handles cleanup & upgrade)
"%VENV_PY%" backend\scripts\ensure_deps.py --quiet
if errorlevel 1 (
    echo Dependency installation failed. Review the messages above.
    pause
    exit /b
)

REM Run the pipeline (preflight is now built-in)
"%VENV_PY%" backend\process_v2.py "%SOURCE_DIR%"

pause
