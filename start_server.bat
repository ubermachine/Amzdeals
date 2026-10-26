@echo off
echo Stopping old server...
wmic process where "commandline like '%%uvicorn main:app%%'" delete 2>nul
timeout /t 2 /nobreak >nul
echo Starting server...
start /B python -m uvicorn main:app --host 0.0.0.0 --port 8000
echo Server started on http://localhost:8000
