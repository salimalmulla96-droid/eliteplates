@echo off
cd /d "%~dp0"
call .venv\Scripts\activate
python desktop_app.py
pause
