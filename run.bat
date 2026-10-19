@echo off
REM Windows: double-click or run "run.bat"
cd /d "%~dp0"
if not exist .env (
  copy .env.example .env >nul
  echo Created .env - paste your OPENAI_API_KEY into it, then run run.bat again.
  pause
  exit /b 1
)
if not exist .venv ( python -m venv .venv )
call .venv\Scripts\activate.bat
pip install -q -r requirements.txt
python run.py
pause
