@echo off
cd /d "D:\roku-apps\roku-backend"
if not exist logs mkdir logs
echo [%date% %time%] Starting Roku backend server>> logs\server.log
uv run python main.py >> logs\server.log 2>&1
