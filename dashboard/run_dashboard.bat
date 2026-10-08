@echo off
rem Start the Ludhiana carbon dashboard at http://localhost:5000 (Windows).
cd /d "%~dp0.."
if exist .venv\Scripts\activate.bat call .venv\Scripts\activate.bat
cd dashboard\backend
python app.py
pause
