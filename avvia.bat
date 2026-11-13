@echo off
rem Ad Library Insights - avvio con doppio clic (Windows).
rem La prima volta crea l'ambiente e installa tutto; dopo apre subito l'app nel browser.
setlocal
cd /d "%~dp0"
title Ad Library Insights

if exist ".venv\Scripts\python.exe" goto run

echo Prima installazione: serve qualche minuto e una connessione a internet.
echo.
where py >nul 2>nul
if %errorlevel%==0 (
    py -3 -m venv .venv
) else (
    python -m venv .venv
)
if not exist ".venv\Scripts\python.exe" (
    echo.
    echo Python non trovato. Installa Python 3.10 o successivo da python.org e riprova.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -e .
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m playwright install chromium
if errorlevel 1 goto failed

:run
echo L'app si apre nel browser. Per chiuderla, chiudi questa finestra.
".venv\Scripts\python.exe" -m ad_library_insights app
if errorlevel 1 pause
exit /b 0

:failed
echo.
echo L'installazione non e' riuscita. Controlla la connessione e riprova.
pause
exit /b 1
