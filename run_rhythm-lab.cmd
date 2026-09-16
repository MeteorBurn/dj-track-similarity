@echo off
setlocal EnableExtensions DisableDelayedExpansion

set "PROJECT_ROOT=%~dp0."
set "MAIN_API=http://127.0.0.1:8765"
set "LAB_URL=http://127.0.0.1:8777/"
set "DEFAULT_DB_PATH=%~dp0database\volumes.sqlite"
set "DB_DIR=%~dp0database"
set "DB_PATH="

if /I "%~1"=="help" goto :usage
if /I "%~1"=="--help" goto :usage
if /I "%~1"=="/?" goto :usage

cd /d "%PROJECT_ROOT%" || goto :setup_error

where curl.exe >nul 2>nul
if errorlevel 1 (
    echo [ERROR] curl.exe is not available on PATH.
    goto :setup_error
)

rem A running main server owns Rhythm Lab: start it there, in that window.
curl.exe -s -o nul --max-time 2 "%MAIN_API%/api/rhythm-lab/status"
if not errorlevel 1 goto :launch_via_main_server

curl.exe -s -o nul --max-time 2 "%LAB_URL%"
if errorlevel 1 goto :start_standalone
echo Rhythm Lab is already running: %LAB_URL%
start "" "%LAB_URL%"
exit /b 0

:launch_via_main_server
echo The main server is running, so Rhythm Lab starts through it
echo on the library selected in the main app.
if not "%~1"=="" echo The database argument is ignored while the main server is running.
echo.
curl.exe -sS --fail-with-body --max-time 150 -X POST "%MAIN_API%/api/rhythm-lab/launch"
if errorlevel 1 goto :main_launch_error
echo.
echo Rhythm Lab: %LAB_URL%
start "" "%LAB_URL%"
exit /b 0

:main_launch_error
echo.
echo [ERROR] The main server could not start Rhythm Lab.
exit /b 1

:start_standalone
if not exist "%PROJECT_ROOT%\.venv\Scripts\python.exe" goto :missing_venv
if not "%~1"=="" set "DB_PATH=%~1"
if not defined DB_PATH call :prompt_database
if exist "%DB_PATH%" goto :database_found
echo [ERROR] Library database not found: "%DB_PATH%"
goto :setup_error

:database_found
echo Starting Rhythm Lab without the main server...
echo.
echo Library: "%DB_PATH%"
echo Open Rhythm Lab: %LAB_URL%
echo.
echo Leave this window open while using Rhythm Lab.
echo Press Ctrl+C to stop it.
echo If you start the main server later, close this window first
echo and launch Rhythm Lab from the main app.
echo.

"%PROJECT_ROOT%\.venv\Scripts\python.exe" "%PROJECT_ROOT%\tools\rhythm-lab\rhythm_lab_cli.py" serve --source "%DB_PATH%" --host 127.0.0.1 --port 8777
set "EXIT_CODE=%ERRORLEVEL%"

echo.
echo Rhythm Lab stopped with exit code %EXIT_CODE%.
exit /b %EXIT_CODE%

:missing_venv
echo [ERROR] Local virtual environment was not found:
echo         %PROJECT_ROOT%\.venv
echo.
echo Create it and install the project first:
echo   uv sync --locked --extra dev
goto :setup_error

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
    set /p "DB_PATH=Library database path [%DEFAULT_DB_PATH%]: "
    echo.
    exit /b 0
)

echo Found library databases in "%DB_DIR%":
set "DEFAULT_CHOICE=1"
for /l %%I in (1,1,!DB_COUNT!) do (
    echo   %%I. !DB_NAME_%%I!
    if /I "!DB_CANDIDATE_%%I!"=="%DEFAULT_DB_PATH%" set "DEFAULT_CHOICE=%%I"
)
echo.
set "DB_CHOICE="
set /p "DB_CHOICE=Library [1-!DB_COUNT!, default !DEFAULT_CHOICE!, or a path]: "
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

:usage
echo Usage:
echo   run_rhythm-lab.cmd
echo   run_rhythm-lab.cmd "C:\path\library.sqlite"
echo.
echo If the main server is running on 127.0.0.1:8765, Rhythm Lab is started
echo through it on the library selected in the main app, so it shares that
echo server's window; a database argument is ignored.
echo If Rhythm Lab is already running, its page is opened.
echo Otherwise Rhythm Lab starts in this window at %LAB_URL% on the given
echo library, or asks which database in "%DB_DIR%" to open.
exit /b 0

:setup_error
echo.
exit /b 1