Set WshShell = CreateObject("WScript.Shell")
WshShell.Run chr(34) & "D:\roku-apps\roku-backend\start_server.bat" & chr(34), 0
Set WshShell = Nothing
