@echo off
setlocal

set "PROJECT_ROOT=%~dp0."
set "HOST=0.0.0.0"
set "PORT=8765"

cd /d "%PROJECT_ROOT%" || goto :pause_error

if not exist "%PROJECT_ROOT%\.venv\Scripts\activate.bat" (
    echo [ERROR] Local virtual environment was not found:
    echo         %PROJECT_ROOT%\.venv
    echo.
    echo Create it and install the project first:
    echo   python -m venv .venv
    echo   .\.venv\Scripts\python.exe -m pip install -e ".[dev]"
    goto :pause_error
)

call "%PROJECT_ROOT%\.venv\Scripts\activate.bat"
if errorlevel 1 goto :pause_error

where dj-sim >nul 2>nul
if errorlevel 1 (
    echo [ERROR] dj-sim is not available in the activated environment.
    echo.
    echo Install the project first:
    echo   .\.venv\Scripts\python.exe -m pip install -e ".[dev]"
    goto :pause_error
)

set "LAN_IP="
for /f "usebackq delims=" %%I in (`powershell -NoProfile -ExecutionPolicy Bypass -Command "$addresses = Get-NetIPAddress -AddressFamily IPv4; foreach ($address in $addresses) { if ($address.IPAddress -notlike '127.*' -and $address.IPAddress -notlike '169.254.*') { $address.IPAddress; break } }"`) do set "LAN_IP=%%I"

echo Starting DJ Track Similarity UI server with local network access...
echo.
echo This computer: http://127.0.0.1:%PORT%/
if defined LAN_IP (
    echo Local network: http://%LAN_IP%:%PORT%/
) else (
    echo Local network: http://^<this-computer-lan-ip^>:%PORT%/
)
echo.
echo Leave this window open while using the UI.
echo Press Ctrl+C to stop the server.
echo If another device cannot connect, allow Python through Windows Firewall.
echo.

dj-sim serve --host %HOST% --port %PORT% %*
set "EXIT_CODE=%ERRORLEVEL%"

echo.
echo Server stopped with exit code %EXIT_CODE%.
pause
exit /b %EXIT_CODE%

:pause_error
echo.
pause
exit /b 1
