@echo off
setlocal
echo Stopping server...
for /f "tokens=*" %%P in ('powershell -NoProfile -Command "(Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess)"') do set BACKEND_PID=%%P
if defined BACKEND_PID (
    echo Killing PID %BACKEND_PID% on port 8000...
    taskkill /F /PID %BACKEND_PID% >nul 2>&1
) else (
    echo No existing listener found on port 8000.
)
ping 127.0.0.1 -n 3 >nul
echo Starting server...
cd /d "D:\roku-apps\roku-backend"
start /MIN cmd /c "D:\roku-apps\roku-backend\start_server.bat"
echo Server restarted in background
ping 127.0.0.1 -n 3 >nul
