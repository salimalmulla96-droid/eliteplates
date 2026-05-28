@echo off
cd /d "%~dp0"

echo Creating local Python environment...
python -m venv .venv

echo Activating environment...
call .venv\Scripts\activate

echo Installing packages...
python -m pip install --upgrade pip
pip install -r requirements.txt

echo.
echo Setup complete.
echo To run the desktop app, double-click run_app.bat or run:
echo run_app.bat
pause
