@echo off
setlocal EnableExtensions DisableDelayedExpansion

set "PROJECT_ROOT=%~dp0."
set "PORT=8765"
set "FRONTEND_PORT=5173"
set "DEFAULT_DB_PATH=%~dp0database\volumes.sqlite"
set "DB_DIR=%~dp0database"
set "DB_PATH="
set "MODE="
set "FRONTEND_HOST="
set "FRONTEND_URL="
set "INTERACTIVE_START=0"

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
    echo   uv sync --locked --extra dev
    goto :setup_error
)

call "%PROJECT_ROOT%\.venv\Scripts\activate.bat"
if errorlevel 1 goto :setup_error

where dj-sim >nul 2>nul
if errorlevel 1 (
    echo [ERROR] dj-sim is not available in the activated environment.
    echo.
    echo Install the project first:
    echo   uv sync --locked --extra dev
    goto :setup_error
)

where npm >nul 2>nul
if errorlevel 1 (
    echo [ERROR] npm is not available on PATH.
    echo.
    echo The launcher starts the live Vite UI so frontend changes are visible
    echo immediately. Install Node.js/npm or start dj-sim serve manually to use
    echo the last built frontend/dist bundle.
    goto :setup_error
)

if /I "%MODE%"=="lan" call :detect_lan_ip

if /I "%MODE%"=="lan" (
    set "FRONTEND_HOST=0.0.0.0"
    if defined LAN_IP (
        set "FRONTEND_URL=http://%LAN_IP%:%FRONTEND_PORT%/"
    ) else (
        set "FRONTEND_URL=http://127.0.0.1:%FRONTEND_PORT%/"
    )
) else (
    set "FRONTEND_HOST=127.0.0.1"
    set "FRONTEND_URL=http://127.0.0.1:%FRONTEND_PORT%/"
)

echo Starting DJ Track Similarity UI server...
echo.
if defined DB_PATH echo Database: "%DB_PATH%"
echo Open UI: %FRONTEND_URL%
echo Backend API: http://127.0.0.1:%PORT%/
if /I "%MODE%"=="lan" (
    if defined LAN_IP (
        echo Local network UI: http://%LAN_IP%:%FRONTEND_PORT%/
    ) else (
        echo Local network UI: http://^<this-computer-lan-ip^>:%FRONTEND_PORT%/
    )
    echo.
    echo Leave this window open while using the UI.
    echo Press Ctrl+C to stop the server.
    echo If another device cannot connect, allow Python and Node.js through Windows Firewall.
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
set "DJ_TRACK_SIMILARITY_LAUNCHER_FRONTEND_DEV=1"
set "DJ_TRACK_SIMILARITY_LAUNCHER_FRONTEND_HOST=%FRONTEND_HOST%"
python "%PROJECT_ROOT%\scripts\run_server_launcher.py" %*
set "EXIT_CODE=%ERRORLEVEL%"

echo.
echo Server stopped with exit code %EXIT_CODE%.
exit /b %EXIT_CODE%

:prompt_database
setlocal EnableDelayedExpansion
set "DB_COUNT=0"
if exist "%DB_DIR%\" (
    for %%F in ("%DB_DIR%\*.sqlite") do (
        if /I "%%~xF"==".sqlite" (
            set /a DB_COUNT+=1
            set "DB_CANDIDATE_!DB_COUNT!=%%~fF"
            set "DB_NAME_!DB_COUNT!=%%~nxF"
        )
    )
)

if "!DB_COUNT!"=="0" (
    endlocal
    set "DB_PATH=%DEFAULT_DB_PATH%"
    set /p "DB_PATH=Database path [%DEFAULT_DB_PATH%]: "
    echo.
    exit /b 0
)

echo Found existing databases in "%DB_DIR%":
set "DEFAULT_CHOICE=1"
for /l %%I in (1,1,!DB_COUNT!) do (
    echo   %%I. !DB_NAME_%%I!
    if /I "!DB_CANDIDATE_%%I!"=="%DEFAULT_DB_PATH%" set "DEFAULT_CHOICE=%%I"
)
echo.
set "DB_CHOICE="
set /p "DB_CHOICE=Database [1-!DB_COUNT!, default !DEFAULT_CHOICE!, or a path]: "
if not defined DB_CHOICE set "DB_CHOICE=!DEFAULT_CHOICE!"

set "SELECTED_PATH="
echo !DB_CHOICE!| findstr /r "^[1-9][0-9]*$" >nul
if not errorlevel 1 if !DB_CHOICE! LEQ !DB_COUNT! (
    for %%N in (!DB_CHOICE!) do set "SELECTED_PATH=!DB_CANDIDATE_%%N!"
)
if not defined SELECTED_PATH set "SELECTED_PATH=!DB_CHOICE!"

endlocal & set "DB_PATH=%SELECTED_PATH%"
echo.
exit /b 0

:prompt_mode
echo Choose server mode:
echo   1. Local only     http://127.0.0.1:%FRONTEND_PORT%/
echo   2. Local network  http://^<this-computer-lan-ip^>:%FRONTEND_PORT%/
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
echo   run_server.cmd local --db "%DEFAULT_DB_PATH%"
echo   run_server.cmd lan --db "%DEFAULT_DB_PATH%"
echo   run_server.cmd local --help
echo.
echo With no arguments, the launcher looks in "%DB_DIR%" first.
echo If it finds one or more .sqlite databases there, it lists them and asks
echo which one to open (or type a path to open/create one elsewhere).
echo If none are found, it asks for a database path: press Enter to create
echo %DEFAULT_DB_PATH%, or type another path to create it there instead.
echo It then asks whether to start in local or LAN mode.
echo Explicit local or lan commands use only the arguments you provide.
exit /b 0

:setup_error
echo.
exit /b 1
