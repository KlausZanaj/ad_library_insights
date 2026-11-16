@echo off
rem Ad Library Insights - start with a double click (Windows).
rem The first time it creates the environment and installs everything; after that it opens the app in the browser right away.
setlocal
cd /d "%~dp0"
title Ad Library Insights

if exist ".venv\Scripts\python.exe" goto run

echo First installation: it takes a few minutes and needs an internet connection.
echo.
where py >nul 2>nul
if %errorlevel%==0 (
    py -3 -m venv .venv
) else (
    python -m venv .venv
)
if not exist ".venv\Scripts\python.exe" (
    echo.
    echo Python not found. Install Python 3.10 or newer from python.org and try again.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -e .
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m playwright install chromium
if errorlevel 1 goto failed

:run
echo The app opens in your browser. To close it, close this window.
".venv\Scripts\python.exe" -m ad_library_insights app
if errorlevel 1 pause
exit /b 0

:failed
echo.
echo The installation failed. Check your connection and try again.
pause
exit /b 1
