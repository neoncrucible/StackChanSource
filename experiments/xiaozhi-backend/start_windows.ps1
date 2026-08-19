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

$ConfigText = Get-Content -Raw $ConfigPath
if ($ConfigText -match "YOUR_WINDOWS_LAN_IP" -or
    $ConfigText -match "REPLACE_WITH_OPENAI_API_KEY" -or
    $ConfigText -match "REPLACE_WITH_GEMINI_API_KEY") {
    throw "Alpha 1 config still contains placeholders. Edit $ConfigPath before starting."
}

Write-Host "=== Kadence 2.0 Alpha 1 / Xiaozhi server ==="
Write-Host "Pinned upstream verified: $PinnedCommit"
Write-Host "Working directory: $ServerDir"
Write-Host "Stop with Ctrl+C."
Write-Host ""

Push-Location $ServerDir
try {
    conda run --no-capture-output -n $CondaEnv python app.py
}
finally {
    Pop-Location
}
