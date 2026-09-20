@echo off
REM One click: bring the log collector up and open Grafana.
REM
REM This is a wrapper around dev-logs.ps1 and holds no logic of its own - it
REM exists because a .cmd runs from Explorer on a double-click and a .ps1 does
REM not, and because -ExecutionPolicy Bypass is needed for an unsigned script.
REM
REM   dev.cmd            start, and open Grafana
REM   dev.cmd -Down      stop; local history is kept
REM   dev.cmd -Clean     stop and discard the local volumes too
REM
REM Arguments are passed straight through, so anything dev-logs.ps1 accepts
REM works here.

setlocal
cd /d "%~dp0"

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0dev-logs.ps1" %*
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
