param(
    [string]$RokuIp = "192.168.1.102"
)

$client = New-Object System.Net.Sockets.TcpClient($RokuIp, 8085)
$stream = $client.GetStream()
$reader = New-Object System.IO.StreamReader($stream)
$buffer = New-Object byte[] 1024

Write-Host "Connected to Roku telnet on $RokuIp port 8085. Reading logs..."
Write-Host "Press Ctrl+C to stop."

while($client.Connected) {
    if($stream.DataAvailable) {
        $bytesRead = $stream.Read($buffer, 0, 1024)
        if($bytesRead -gt 0) {
            $output = [System.Text.Encoding]::ASCII.GetString($buffer, 0, $bytesRead)
            Write-Host $output -NoNewline
        }
    }
    Start-Sleep -Milliseconds 100
}

$client.Close()
Write-Host "Connection closed."
