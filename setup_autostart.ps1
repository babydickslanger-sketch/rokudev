# PowerShell script to set up the Roku backend server to run automatically at startup
# Run this script as Administrator

$scriptPath = "D:\roku-apps\roku-backend\start_server_hidden.vbs"
$taskName = "RokuBackendServer"

Write-Host "Setting up Roku Backend Server to run at startup..." -ForegroundColor Green

# Check if task already exists
$existingTask = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue

if ($existingTask) {
    Write-Host "Task '$taskName' already exists. Removing it..." -ForegroundColor Yellow
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

# Create the scheduled task
$action = New-ScheduledTaskAction -Execute "wscript.exe" -Argument "`"$scriptPath`""
$trigger = New-ScheduledTaskTrigger -AtLogon
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -RunLevel Highest -Force

Write-Host "Task '$taskName' has been created successfully!" -ForegroundColor Green
Write-Host "The backend server will now start automatically when you log in." -ForegroundColor Cyan
Write-Host ""
Write-Host "To test it immediately, run: Start-ScheduledTask -TaskName '$taskName'" -ForegroundColor Yellow
Write-Host "To remove it later, run: Unregister-ScheduledTask -TaskName '$taskName' -Confirm:`$false" -ForegroundColor Yellow
