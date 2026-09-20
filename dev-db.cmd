@echo off
REM One click: the development PostgreSQL every app on this machine uses.
REM
REM A wrapper around dev-db.ps1 holding no logic of its own - Explorer runs a
REM .cmd on a double-click and will not run a .ps1, and an unsigned script needs
REM -ExecutionPolicy Bypass.
REM
REM   dev-db.cmd             start it
REM   dev-db.cmd -Down       stop and remove the container; the VOLUME STAYS
REM   dev-db.cmd -Migrate    one-off: copy the old anime_site volume into this one
REM
REM Arguments pass straight through.

setlocal
cd /d "%~dp0"

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0dev-db.ps1" %*
set RC=%ERRORLEVEL%

if not "%RC%"=="0" (
    echo.
    echo ---------------------------------------------------------------
    echo  It failed with exit code %RC%.
    echo.
    echo  This window is being held open on purpose: launched from
    echo  Explorer it would otherwise close instantly and take the only
    echo  explanation with it.
    echo ---------------------------------------------------------------
    echo.
    pause
)

endlocal
exit /b %RC%
