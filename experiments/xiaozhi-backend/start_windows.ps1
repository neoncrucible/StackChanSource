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
$Utf8NoBom = [System.Text.UTF8Encoding]::new($false)

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

function Resolve-KadenceFfmpegBin {
    $Configured = [Environment]::GetEnvironmentVariable("KADENCE_FFMPEG_BIN")
    if (-not [string]::IsNullOrWhiteSpace($Configured)) {
        $Candidate = Join-Path $Configured "ffmpeg.exe"
        if (Test-Path $Candidate) {
            return $Configured.Trim()
        }
        throw "KADENCE_FFMPEG_BIN is set, but ffmpeg.exe was not found at $Candidate"
    }

    $ToolsRoot = Join-Path $PSScriptRoot ".tools\ffmpeg"
    if (Test-Path $ToolsRoot) {
        $Standalone = Get-ChildItem $ToolsRoot -Recurse -Filter "ffmpeg.exe" -File -ErrorAction SilentlyContinue |
            Select-Object -First 1
        if ($null -ne $Standalone) {
            return $Standalone.DirectoryName
        }
    }

    return $null
}

function Resolve-CondaEnvPrefix {
    param([Parameter(Mandatory = $true)][string]$EnvironmentName)

    $JsonText = (& conda env list --json) -join "`n"
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to enumerate Conda environments."
    }

    $EnvList = $JsonText | ConvertFrom-Json
    foreach ($EnvPath in $EnvList.envs) {
        if ((Split-Path $EnvPath -Leaf) -eq $EnvironmentName) {
            return $EnvPath
        }
    }

    throw "Conda environment '$EnvironmentName' was not found. Run bootstrap_windows.ps1 first."
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

$RuntimePatchScript = Join-Path $PSScriptRoot "patch_runtime_luna_windows.ps1"
if (-not (Test-Path $RuntimePatchScript)) {
    throw "Missing active Luna runtime compatibility patch script: $RuntimePatchScript"
}
& $RuntimePatchScript -RepoDir $RepoDir

# The upstream loader reads YAML literally; it does not expand environment
# variables. Kadence now has one cloud credential source: OpenAI, shared by Luna
# and Realtime ASR. Keep it only in the ignored local runtime copy.
$ConfigText = [System.IO.File]::ReadAllText($ConfigPath, $Utf8NoBom)
$ConfigChanged = $false

if ($ConfigText.Contains("REPLACE_WITH_OPENAI_API_KEY")) {
    $OpenAiKey = Read-SecretValue -EnvironmentName "KADENCE_OPENAI_API_KEY" -Prompt "OpenAI API key for Kadence Luna / Realtime ASR"
    if ([string]::IsNullOrWhiteSpace($OpenAiKey)) {
        throw "OpenAI API key was empty."
    }
    $ConfigText = $ConfigText.Replace("REPLACE_WITH_OPENAI_API_KEY", $OpenAiKey)
    $ConfigChanged = $true
}

if ($ConfigChanged) {
    [System.IO.File]::WriteAllText($ConfigPath, $ConfigText, $Utf8NoBom)
    Write-Host "Stored Kadence OpenAI credential only in the ignored local runtime config."
}

if ($ConfigText -match "REPLACE_WITH_[A-Z0-9_]+") {
    throw "Kadence config still contains an unresolved credential placeholder."
}

$RealtimeInstaller = Join-Path $PSScriptRoot "enable_realtime_asr_windows.ps1"
if (-not (Test-Path $RealtimeInstaller)) {
    throw "Missing Realtime ASR installer: $RealtimeInstaller"
}
& $RealtimeInstaller -RuntimeRoot $RuntimeRoot

$FfmpegBin = Resolve-KadenceFfmpegBin
if ($null -ne $FfmpegBin) {
    $FfmpegExe = Join-Path $FfmpegBin "ffmpeg.exe"
    Write-Host "Using standalone FFmpeg: $FfmpegExe"
    & $FfmpegExe -version *> $null
    if ($LASTEXITCODE -ne 0) {
        throw "Standalone FFmpeg preflight failed with exit code ${LASTEXITCODE}: $FfmpegExe"
    }
}

$CondaPrefix = Resolve-CondaEnvPrefix -EnvironmentName $CondaEnv
$PythonExe = Join-Path $CondaPrefix "python.exe"
if (-not (Test-Path $PythonExe)) {
    throw "Python was not found in Conda environment '$CondaEnv': $PythonExe"
}

# Preserve the proven UDP discovery bridge and frozen robot transport contract.
$Probe = $null
try {
    $Probe = [System.Net.Sockets.UdpClient]::new($DiscoveryPort)
}
catch {
    throw "UDP discovery port $DiscoveryPort is already in use. Stop the old Kadence voice server before starting Alpha 2."
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
Write-Host "Conda environment: $CondaPrefix"
Write-Host "Discovery bridge: UDP $DiscoveryPort -> ws://<this-PC>:$XiaozhiPort$XiaozhiPath"
Write-Host "Working directory: $ServerDir"
Write-Host "Stop with Ctrl+C."
Write-Host ""

$OriginalPath = $env:Path
$OriginalCondaPrefix = $env:CONDA_PREFIX
$OriginalCondaDefaultEnv = $env:CONDA_DEFAULT_ENV

$EnvPathParts = @()
if ($null -ne $FfmpegBin) {
    $EnvPathParts += $FfmpegBin
}
$EnvPathParts += @(
    $CondaPrefix,
    (Join-Path $CondaPrefix "Scripts"),
    (Join-Path $CondaPrefix "Library\bin")
)
$env:Path = (($EnvPathParts + $OriginalPath) -join ";")
$env:CONDA_PREFIX = $CondaPrefix
$env:CONDA_DEFAULT_ENV = $CondaEnv

Push-Location $ServerDir
try {
    if ($null -ne $FfmpegBin) {
        $ResolvedFfmpeg = (& $PythonExe -c "import shutil; print(shutil.which('ffmpeg') or '')").Trim()
        if ($ResolvedFfmpeg -ne $FfmpegExe) {
            throw "Python resolved the wrong FFmpeg. Expected '$FfmpegExe', got '$ResolvedFfmpeg'."
        }
    }

    & $PythonExe app.py
    if ($LASTEXITCODE -ne 0) {
        throw "Xiaozhi server exited with code $LASTEXITCODE."
    }
}
finally {
    Pop-Location
    $env:Path = $OriginalPath
    $env:CONDA_PREFIX = $OriginalCondaPrefix
    $env:CONDA_DEFAULT_ENV = $OriginalCondaDefaultEnv
    if ($null -ne $DiscoveryJob) {
        Stop-Job $DiscoveryJob -ErrorAction SilentlyContinue
        Remove-Job $DiscoveryJob -Force -ErrorAction SilentlyContinue
    }
}
