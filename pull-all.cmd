@echo off
REM One click: git pull the platform and every app cloned inside it.
REM
REM A wrapper around pull-all.ps1 holding no logic of its own - Explorer runs a
REM .cmd on a double-click and will not run a .ps1, and an unsigned script needs
REM -ExecutionPolicy Bypass.
REM
REM   pull-all.cmd              pull every repository on its current branch
REM   pull-all.cmd -FetchOnly   fetch every repository; touch no checkout
REM
REM Arguments pass straight through.

setlocal
cd /d "%~dp0"

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0pull-all.ps1" %*
set RC=%ERRORLEVEL%

if not "%RC%"=="0" (
    echo.
    echo ---------------------------------------------------------------
    echo  At least one repository was not pulled - see the summary.
    echo.
    echo  This window is being held open on purpose: launched from
    echo  Explorer it would otherwise close instantly and take the only
    echo  explanation with it.
    echo ---------------------------------------------------------------
    echo.
    pause
)

REM On one line: %RC% expands before endlocal discards it. On two, the exit
REM code is always 0.
endlocal & exit /b %RC%
