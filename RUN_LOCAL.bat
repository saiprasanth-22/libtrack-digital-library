@echo off
setlocal
cd /d "%~dp0"
if not defined LIBTRACK_PORT set "LIBTRACK_PORT=8000"

title LibTrack Local Server
color 0A

echo.
echo  ============================================================
echo                    LIBTRACK LOCAL SERVER
echo  ============================================================
echo.
echo  IMPORTANT: Extract the GitHub ZIP before running this file.
echo.

if not exist "manage.py" goto :not_extracted

where py >nul 2>nul
if %errorlevel%==0 (
    set "PYTHON_CMD=py -3"
) else (
    where python >nul 2>nul
    if errorlevel 1 goto :python_missing
    set "PYTHON_CMD=python"
)

if not exist ".venv\Scripts\python.exe" (
    echo  [1/5] Creating the private Python environment...
    %PYTHON_CMD% -m venv .venv
    if errorlevel 1 goto :failed
) else (
    echo  [1/5] Python environment already exists.
)

set "VENV_PYTHON=%CD%\.venv\Scripts\python.exe"
set "LIBTRACK_SQLITE_PATH=%CD%\demo.sqlite3"

echo  [2/5] Installing required packages...
"%VENV_PYTHON%" -m pip install --disable-pip-version-check -q -r requirements.txt
if errorlevel 1 goto :failed

echo  [3/5] Opening the persistent local database...
if not exist "demo.sqlite3" goto :database_missing
"%VENV_PYTHON%" manage.py migrate --noinput
if errorlevel 1 goto :failed

echo  [4/5] Your books, users and transactions are saved automatically.

echo  [5/5] Starting LibTrack...
echo.
echo  ============================================================
echo   WEBSITE:          http://127.0.0.1:%LIBTRACK_PORT%
echo.
echo   STUDENT LOGIN:    student
echo   PASSWORD:         1
echo.
echo   LIBRARIAN LOGIN:  admin
echo   PASSWORD:         1
echo  ============================================================
echo.
echo  Keep this window open while presenting the website.
echo  Press CTRL+C when you want to stop the server.
echo.

if not defined LIBTRACK_NO_BROWSER start "" "http://127.0.0.1:%LIBTRACK_PORT%"
"%VENV_PYTHON%" manage.py runserver 127.0.0.1:%LIBTRACK_PORT%
goto :end

:not_extracted
echo  ERROR: manage.py was not found beside RUN_LOCAL.bat.
echo  Right-click the downloaded ZIP, choose "Extract All", then run
echo  RUN_LOCAL.bat from inside the extracted project folder.
goto :pause_error

:python_missing
echo  ERROR: Python 3 is not installed or is not available in PATH.
echo  Install Python 3 from https://www.python.org/downloads/
echo  During installation, enable "Add Python to PATH".
goto :pause_error

:database_missing
echo  ERROR: demo.sqlite3 was not found beside RUN_LOCAL.bat.
echo  Download and extract the complete source ZIP again.
goto :pause_error

:failed
echo.
echo  ERROR: Setup could not finish. Read the message above for the cause.

:pause_error
echo.
pause
exit /b 1

:end
endlocal
