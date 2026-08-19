param(
    [string]$RuntimeRoot = (Join-Path $PSScriptRoot ".runtime"),
    [string]$CondaEnv = "kadence2-xiaozhi"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$PinnedCommit = "e1876f1ce19cad6e7bfd7c80e41dc56b2e858dd5"
$RepoDir = Join-Path $RuntimeRoot "xiaozhi-esp32-server"
$ServerDir = Join-Path $RepoDir "main\xiaozhi-server"
$ConfigPath = Join-Path $ServerDir "data\.config.yaml"
$DiscoveryPort = 45872
$XiaozhiPort = 8000
$XiaozhiPath = "/xiaozhi/v1/"

function Read-SecretValue {
    param(
        [Parameter(Mandatory = $true)][string]$EnvironmentName,
        [Parameter(Mandatory = $true)][string]$Prompt
    )

    $Existing = [Environment]::GetEnvironmentVariable($EnvironmentName)
    if (-not [string]::IsNullOrWhiteSpace($Existing)) {
        return $Existing.Trim()
    }

    $Secure = Read-Host $Prompt -AsSecureString
    $Bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Secure)
    try {
        return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($Bstr).Trim()
    }
    finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($Bstr)
    }
}

if (-not (Get-Command conda -ErrorAction SilentlyContinue)) {
    throw "conda was not found in PATH. Run this from an Anaconda/Miniconda PowerShell or Prompt."
}

if (-not (Test-Path $ServerDir)) {
    throw "Xiaozhi runtime not found. Run bootstrap_windows.ps1 first."
}

$ActualCommit = (git -C $RepoDir rev-parse HEAD).Trim()
if ($ActualCommit -ne $PinnedCommit) {
    throw "Runtime is not on the Alpha 1 pinned commit. Expected $PinnedCommit, got $ActualCommit"
}

if (-not (Test-Path $ConfigPath)) {
    throw "Missing $ConfigPath. Run bootstrap_windows.ps1 first."
}

# The upstream loader reads YAML literally; it does not expand environment
# variables. Keep the example placeholders in Git, then inject secrets only into
# the ignored .runtime copy. Environment variables avoid prompting on later runs:
#   KADENCE_OPENAI_API_KEY
#   KADENCE_GEMINI_API_KEY
$ConfigText = Get-Content -Raw $ConfigPath
$ConfigChanged = $false

if ($ConfigText.Contains("REPLACE_WITH_OPENAI_API_KEY")) {
    $OpenAiKey = Read-SecretValue \
        -EnvironmentName "KADENCE_OPENAI_API_KEY" \
        -Prompt "OpenAI API key for Alpha 1 speech recognition"
    if ([string]::IsNullOrWhiteSpace($OpenAiKey)) {
        throw "OpenAI API key was empty."
    }
    $ConfigText = $ConfigText.Replace("REPLACE_WITH_OPENAI_API_KEY", $OpenAiKey)
    $ConfigChanged = $true
}

if ($ConfigText.Contains("REPLACE_WITH_GEMINI_API_KEY")) {
    $GeminiKey = Read-SecretValue \
        -EnvironmentName "KADENCE_GEMINI_API_KEY" \
        -Prompt "Gemini API key for Alpha 1 LLM"
    if ([string]::IsNullOrWhiteSpace($GeminiKey)) {
        throw "Gemini API key was empty."
    }
    $ConfigText = $ConfigText.Replace("REPLACE_WITH_GEMINI_API_KEY", $GeminiKey)
    $ConfigChanged = $true
}

if ($ConfigChanged) {
    Set-Content -Path $ConfigPath -Value $ConfigText -Encoding UTF8
    Write-Host "Stored Alpha 1 credentials only in the ignored local runtime config."
}

if ($ConfigText -match "REPLACE_WITH_[A-Z0-9_]+") {
    throw "Alpha 1 config still contains an unresolved credential placeholder."
}

# Kadence Beta already discovers its Windows voice service by UDP broadcast.
# Preserve that proven firmware behaviour for Alpha 1: this tiny bridge answers
# the existing discovery packet but points the robot at Xiaozhi's native
# WebSocket endpoint. It means the PC's DHCP address can change without a
# firmware rebuild or hard-coded IP.
$Probe = $null
try {
    $Probe = [System.Net.Sockets.UdpClient]::new($DiscoveryPort)
}
catch {
    throw "UDP discovery port $DiscoveryPort is already in use. Stop the old Kadence voice server before starting Alpha 1."
}
finally {
    if ($null -ne $Probe) {
        $Probe.Close()
    }
}

$DiscoveryJob = Start-Job -ArgumentList $DiscoveryPort, $XiaozhiPort, $XiaozhiPath -ScriptBlock {
    param($ListenPort, $ServerPort, $ServerPath)

    $Udp = [System.Net.Sockets.UdpClient]::new($ListenPort)
    $Utf8 = [System.Text.Encoding]::UTF8
    try {
        while ($true) {
            $Remote = [System.Net.IPEndPoint]::new([System.Net.IPAddress]::Any, 0)
            $Packet = $Udp.Receive([ref]$Remote)
            $Request = $Utf8.GetString($Packet)
            if ($Request -ne "KADENCE_DISCOVER_V1") {
                continue
            }

            $ReplyText = "KADENCE_SERVER_V1 $ServerPort $ServerPath"
            $Reply = $Utf8.GetBytes($ReplyText)
            [void]$Udp.Send($Reply, $Reply.Length, $Remote)
        }
    }
    finally {
        $Udp.Close()
    }
}

Write-Host "=== Kadence 2.0 Alpha 1 / Xiaozhi server ==="
Write-Host "Pinned upstream verified: $PinnedCommit"
Write-Host "Discovery bridge: UDP $DiscoveryPort -> ws://<this-PC>:$XiaozhiPort$XiaozhiPath"
Write-Host "Working directory: $ServerDir"
Write-Host "Stop with Ctrl+C."
Write-Host ""

Push-Location $ServerDir
try {
    conda run --no-capture-output -n $CondaEnv python app.py
}
finally {
    Pop-Location
    if ($null -ne $DiscoveryJob) {
        Stop-Job $DiscoveryJob -ErrorAction SilentlyContinue
        Remove-Job $DiscoveryJob -Force -ErrorAction SilentlyContinue
    }
}
