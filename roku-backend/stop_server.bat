@echo off
setlocal
for /f "tokens=*" %%P in ('powershell -NoProfile -Command "(Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess)"') do set BACKEND_PID=%%P
if defined BACKEND_PID (
    echo Stopping Roku backend process on port 8000 with PID %BACKEND_PID%...
    taskkill /F /PID %BACKEND_PID%
) else (
    echo No process is currently listening on port 8000.
)
echo Roku Backend Server stopped
pause
