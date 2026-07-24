@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "PROJECT_ROOT=%~dp0."
set "PORT=8765"
set "MODE="
set "PROMPT_ON_EXIT=0"

if /I "%~1"=="help" goto :usage
if /I "%~1"=="--help" goto :usage
if /I "%~1"=="/?" goto :usage

if /I "%~1"=="local" set "MODE=local" & shift /1 & goto :mode_selected
if /I "%~1"=="localhost" set "MODE=local" & shift /1 & goto :mode_selected
if /I "%~1"=="127.0.0.1" set "MODE=local" & shift /1 & goto :mode_selected
if /I "%~1"=="--local" set "MODE=local" & shift /1 & goto :mode_selected
if /I "%~1"=="lan" set "MODE=lan" & shift /1 & goto :mode_selected
if /I "%~1"=="network" set "MODE=lan" & shift /1 & goto :mode_selected
if /I "%~1"=="0.0.0.0" set "MODE=lan" & shift /1 & goto :mode_selected
if /I "%~1"=="--lan" set "MODE=lan" & shift /1 & goto :mode_selected

:mode_selected
if not defined MODE (
    set "PROMPT_ON_EXIT=1"
    call :prompt_mode
)

if /I "%MODE%"=="lan" (
    set "HOST=0.0.0.0"
) else (
    set "MODE=local"
    set "HOST=127.0.0.1"
)

set "FORWARDED_ARGS="

:collect_args
if "%~1"=="" goto :args_done
set "ARG=%~1"
set "FORWARDED_ARGS=!FORWARDED_ARGS! ^"!ARG!^""
shift /1
goto :collect_args

:args_done
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

dj-sim serve --host %HOST% --port %PORT% %FORWARDED_ARGS%
set "EXIT_CODE=%ERRORLEVEL%"

echo.
echo Server stopped with exit code %EXIT_CODE%.
if "%PROMPT_ON_EXIT%"=="1" pause
exit /b %EXIT_CODE%

:prompt_mode
echo DJ Track Similarity UI server
echo.
echo Choose server mode:
echo   1. Local only     http://127.0.0.1:%PORT%/
echo   2. Local network  http://^<this-computer-lan-ip^>:%PORT%/
echo.
set /p "MODE_CHOICE=Mode [1/2, default 1]: "
if /I "%MODE_CHOICE%"=="2" set "MODE=lan" & exit /b 0
if /I "%MODE_CHOICE%"=="lan" set "MODE=lan" & exit /b 0
if /I "%MODE_CHOICE%"=="network" set "MODE=lan" & exit /b 0
set "MODE=local"
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
echo   run_server.cmd local
echo   run_server.cmd local --db C:\db\abstracted.sqlite
echo   run_server.cmd lan --db C:\db\abstracted.sqlite
echo   run_server.cmd local --help
echo.
echo Without --db, the server starts without a selected database.
echo Choose or create a database through the UI.
exit /b 0

:setup_error
echo.
if "%PROMPT_ON_EXIT%"=="1" pause
exit /b 1
