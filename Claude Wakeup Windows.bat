@echo off
setlocal

cd /d "%~dp0"

rem Try the Windows Python launcher first, then fall back to python.
where py >nul 2>nul
if %errorlevel%==0 (
    py -3 claude_wakeup_gui.py
    goto :end
)

where python >nul 2>nul
if %errorlevel%==0 (
    python claude_wakeup_gui.py
    goto :end
)

echo Python was not found in PATH.
echo Install Python 3 and try again.
pause

:end
endlocal
