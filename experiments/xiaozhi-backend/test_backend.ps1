param(
    [string]$HostAddress = "127.0.0.1",
    [int]$XiaozhiPort = 8000,
    [int]$DiscoveryPort = 45872
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

Write-Host "=== Kadence 2.0 Alpha 1 / backend preflight ==="

# 1. Xiaozhi TCP listener.
$Tcp = [System.Net.Sockets.TcpClient]::new()
try {
    $Connect = $Tcp.BeginConnect($HostAddress, $XiaozhiPort, $null, $null)
    if (-not $Connect.AsyncWaitHandle.WaitOne(2000)) {
        throw "Timed out connecting to Xiaozhi TCP $HostAddress`:$XiaozhiPort"
    }
    $Tcp.EndConnect($Connect)
    Write-Host "PASS  Xiaozhi TCP listener is reachable on $HostAddress`:$XiaozhiPort"
}
finally {
    $Tcp.Close()
}

# 2. The exact UDP discovery exchange used by the existing Kadence firmware.
$Udp = [System.Net.Sockets.UdpClient]::new()
try {
    $Udp.EnableBroadcast = $true
    $Udp.Client.ReceiveTimeout = 2500

    $Utf8 = [System.Text.Encoding]::UTF8
    $RequestText = "KADENCE_DISCOVER_V1"
    $Request = $Utf8.GetBytes($RequestText)
    $Destination = [System.Net.IPEndPoint]::new(
        [System.Net.IPAddress]::Broadcast,
        $DiscoveryPort
    )

    [void]$Udp.Send($Request, $Request.Length, $Destination)

    $Remote = [System.Net.IPEndPoint]::new([System.Net.IPAddress]::Any, 0)
    $ReplyBytes = $Udp.Receive([ref]$Remote)
    $Reply = $Utf8.GetString($ReplyBytes)

    $Expected = "KADENCE_SERVER_V1 $XiaozhiPort /xiaozhi/v1/"
    if ($Reply -ne $Expected) {
        throw "Unexpected discovery reply '$Reply' from $($Remote.Address). Expected '$Expected'."
    }

    Write-Host "PASS  Kadence UDP discovery returned $Reply"
    Write-Host "PASS  Discovery responder address: $($Remote.Address)"
}
catch [System.Net.Sockets.SocketException] {
    throw "Kadence UDP discovery did not answer within 2.5 seconds. Check that start_windows.ps1 is running and Windows Firewall allows the private network."
}
finally {
    $Udp.Close()
}

Write-Host ""
Write-Host "Backend preflight passed. The PC side is ready for the Alpha firmware test."
