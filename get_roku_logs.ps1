$client = New-Object System.Net.Sockets.TcpClient
$client.Connect("192.168.1.102", 8085)
$stream = $client.GetStream()
$reader = New-Object System.IO.StreamReader($stream)
$writer = New-Object System.IO.StreamWriter($stream)
$writer.AutoFlush = $true
Start-Sleep -Milliseconds 500
$output = $reader.ReadToEnd()
$client.Close()
Write-Output $output
