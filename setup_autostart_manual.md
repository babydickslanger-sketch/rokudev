# How to Set Up Automatic Backend Server Startup on Windows

## Option 1: Automated Setup (Recommended)

Run the PowerShell script as Administrator:

```powershell
# Right-click on PowerShell and select "Run as Administrator"
cd D:\roku-apps
.\setup_autostart.ps1
```

This will:
- Create a Windows Scheduled Task
- Configure it to run automatically when you log in
- Run the server in the background (hidden window)

## Option 2: Manual Setup via Task Scheduler

1. Open **Task Scheduler** (search for it in Windows)
2. Click **Create Basic Task** on the right
3. Name it: `Roku Backend Server`
4. Trigger: **When I log on**
5. Action: **Start a program**
6. Program/script: `wscript.exe`
7. Add arguments: `"D:\roku-apps\roku-backend\start_server_hidden.vbs"`
8. Click **Finish**

## Option 3: Windows Startup Folder

1. Press `Win + R` and type: `shell:startup`
2. Create a shortcut to: `D:\roku-apps\roku-backend\start_server_hidden.vbs`
3. The server will start automatically when you log in

## Verification

To verify the server is running:
```powershell
# Check if the process is running
Get-Process python | Where-Object {$_.Path -like "*roku-backend*"}

# Test the server
curl http://localhost:8000/health
```

## To Stop Auto-Start

```powershell
# Remove the scheduled task
Unregister-ScheduledTask -TaskName "RokuBackendServer" -Confirm:$false

# Or delete the shortcut from the Startup folder
```

## Troubleshooting

If the server doesn't start automatically:
1. Check Task Scheduler history for errors
2. Ensure the path `D:\roku-apps\roku-backend\` exists
3. Ensure Python virtual environment is properly set up
4. Test running `start_server.bat` manually first
