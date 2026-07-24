@echo off
setlocal EnableExtensions DisableDelayedExpansion

set "PROJECT_ROOT=%~dp0."
set "PORT=8765"
set "DEFAULT_DB_PATH=C:\db\volumes.sqlite"
set "DB_PATH="
set "MODE="
set "INTERACTIVE_START=0"
set "PROMPT_ON_EXIT=0"

if "%~1"=="" set "INTERACTIVE_START=1"

if /I "%~1"=="help" goto :usage
if /I "%~1"=="--help" goto :usage
if /I "%~1"=="/?" goto :usage

if /I "%~1"=="local" goto :select_local
if /I "%~1"=="localhost" goto :select_local
if /I "%~1"=="127.0.0.1" goto :select_local
if /I "%~1"=="--local" goto :select_local
if /I "%~1"=="lan" goto :select_lan
if /I "%~1"=="network" goto :select_lan
if /I "%~1"=="0.0.0.0" goto :select_lan
if /I "%~1"=="--lan" goto :select_lan
goto :mode_selected

:select_local
set "MODE=local"
goto :mode_selected

:select_lan
set "MODE=lan"
goto :mode_selected

:mode_selected
if not defined MODE (
    set "PROMPT_ON_EXIT=1"
    echo DJ Track Similarity UI server
    echo.
    if "%INTERACTIVE_START%"=="1" call :prompt_database
    call :prompt_mode
)

if /I "%MODE%"=="lan" (
    set "HOST=0.0.0.0"
) else (
    set "MODE=local"
    set "HOST=127.0.0.1"
)

cd /d "%PROJECT_ROOT%" || goto :setup_error

if not exist "%PROJECT_ROOT%\.venv\Scripts\activate.bat" (
    echo [ERROR] Local virtual environment was not found:
    echo         %PROJECT_ROOT%\.venv
    echo.
    echo Create it and install the project first:
    echo   python -m venv .venv
    echo   .\.venv\Scripts\python.exe -m pip install -e ".[dev]"
    goto :setup_error
)

call "%PROJECT_ROOT%\.venv\Scripts\activate.bat"
if errorlevel 1 goto :setup_error

where dj-sim >nul 2>nul
if errorlevel 1 (
    echo [ERROR] dj-sim is not available in the activated environment.
    echo.
    echo Install the project first:
    echo   .\.venv\Scripts\python.exe -m pip install -e ".[dev]"
    goto :setup_error
)

if /I "%MODE%"=="lan" call :detect_lan_ip

echo Starting DJ Track Similarity UI server...
echo.
if defined DB_PATH echo Database: "%DB_PATH%"
echo This computer: http://127.0.0.1:%PORT%/
if /I "%MODE%"=="lan" (
    if defined LAN_IP (
        echo Local network: http://%LAN_IP%:%PORT%/
    ) else (
        echo Local network: http://^<this-computer-lan-ip^>:%PORT%/
    )
    echo.
    echo Leave this window open while using the UI.
    echo Press Ctrl+C to stop the server.
    echo If another device cannot connect, allow Python through Windows Firewall.
) else (
    echo Local mode only. Other devices on the LAN cannot connect to this process.
    echo.
    echo Leave this window open while using the UI.
    echo Press Ctrl+C to stop the server.
)
echo.

set "DJ_TRACK_SIMILARITY_LAUNCHER_HOST=%HOST%"
set "DJ_TRACK_SIMILARITY_LAUNCHER_PORT=%PORT%"
set "DJ_TRACK_SIMILARITY_LAUNCHER_DATABASE=%DB_PATH%"
python "%PROJECT_ROOT%\scripts\run_server_launcher.py" %*
set "EXIT_CODE=%ERRORLEVEL%"

echo.
echo Server stopped with exit code %EXIT_CODE%.
if "%PROMPT_ON_EXIT%"=="1" pause
exit /b %EXIT_CODE%

:prompt_database
set "DB_PATH=%DEFAULT_DB_PATH%"
set /p "DB_PATH=Database path [%DEFAULT_DB_PATH%]: "
echo.
exit /b 0

:prompt_mode
echo Choose server mode:
echo   1. Local only     http://127.0.0.1:%PORT%/
echo   2. Local network  http://^<this-computer-lan-ip^>:%PORT%/
echo.
set "MODE_CHOICE="
set /p "MODE_CHOICE=Mode [1/2, default 1]: "
if /I "%MODE_CHOICE%"=="2" goto :prompt_lan_selected
if /I "%MODE_CHOICE%"=="lan" goto :prompt_lan_selected
if /I "%MODE_CHOICE%"=="network" goto :prompt_lan_selected
set "MODE=local"
exit /b 0

:prompt_lan_selected
set "MODE=lan"
exit /b 0

:detect_lan_ip
set "LAN_IP="
for /f "usebackq delims=" %%I in (`powershell -NoProfile -ExecutionPolicy Bypass -Command "$addresses = Get-NetIPAddress -AddressFamily IPv4; foreach ($address in $addresses) { if ($address.IPAddress -notlike '127.*' -and $address.IPAddress -notlike '169.254.*') { $address.IPAddress; break } }"`) do set "LAN_IP=%%I"
exit /b 0

:usage
echo Usage:
echo   run_server.cmd
echo   run_server.cmd local [dj-sim serve options]
echo   run_server.cmd lan [dj-sim serve options]
echo.
echo Examples:
echo   run_server.cmd
echo   run_server.cmd local --db C:\db\volumes.sqlite
echo   run_server.cmd lan --db C:\db\volumes.sqlite
echo   run_server.cmd local --help
echo.
echo With no arguments, the launcher asks for a database path first.
echo Press Enter to accept C:\db\volumes.sqlite, or type another path.
echo It then asks whether to start in local or LAN mode.
echo Explicit local or lan commands use only the arguments you provide.
exit /b 0

:setup_error
echo.
if "%PROMPT_ON_EXIT%"=="1" pause
exit /b 1
