@echo off
cd /d "%~dp0.."
if not exist ".venv\Scripts\activate.bat" (
    echo [ERROR] Local virtual environment was not found:
    echo         %CD%\.venv
    echo.
    echo Create it and install the project first:
    echo   python -m venv .venv
    echo   .\.venv\Scripts\python.exe -m pip install -e ".[dev]"
    exit /b 1
)

call ".venv\Scripts\activate.bat"
if errorlevel 1 exit /b 1

where dj-sim >nul 2>nul
if errorlevel 1 (
    echo [ERROR] dj-sim is not available in the activated environment.
    echo.
    echo Install the project first:
    echo   .\.venv\Scripts\python.exe -m pip install -e ".[dev]"
    exit /b 1
)

dj-sim serve --host 127.0.0.1 --port 8765 %*
