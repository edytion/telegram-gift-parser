@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONUTF8=1
if not exist ".venv\Scripts\python.exe" (
  py -3 -m venv .venv
  if errorlevel 1 goto failed
)
.venv\Scripts\python.exe -c "import telethon; assert telethon.__version__ == '1.45.0'" >nul 2>&1
if errorlevel 1 (
  .venv\Scripts\python.exe -m pip install --quiet -r requirements.txt
  if errorlevel 1 goto failed
)
.venv\Scripts\python.exe gift-parser.py %*
if errorlevel 3 goto failed
if errorlevel 2 goto incomplete
if errorlevel 1 goto failed
pause
exit /b 0
:incomplete
echo Collection finished with incomplete data. See logs.
pause
exit /b 2
:failed
echo STOP. See logs\errors.log and logs\latest.log.
pause
exit /b 1
