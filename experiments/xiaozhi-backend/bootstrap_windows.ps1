param(
    [string]$RuntimeRoot = (Join-Path $PSScriptRoot ".runtime"),
    [string]$CondaEnv = "kadence2-xiaozhi",
    [switch]$ResetRuntime
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Upstream = "https://github.com/xinnan-tech/xiaozhi-esp32-server.git"
$PinnedCommit = "e1876f1ce19cad6e7bfd7c80e41dc56b2e858dd5"
$RepoDir = Join-Path $RuntimeRoot "xiaozhi-esp32-server"
$ServerDir = Join-Path $RepoDir "main\xiaozhi-server"
$DataDir = Join-Path $ServerDir "data"
$ConfigSource = Join-Path $PSScriptRoot "kadence.config.example.yaml"
$ConfigTarget = Join-Path $DataDir ".config.yaml"

function Require-Command([string]$Name) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required command '$Name' was not found in PATH."
    }
}

Write-Host "=== Kadence 2.0 Alpha 1 / Xiaozhi bootstrap ==="
Write-Host "Pinned upstream: $PinnedCommit"

Require-Command git
Require-Command conda

if ($ResetRuntime -and (Test-Path $RepoDir)) {
    Write-Host "Removing existing experimental runtime..."
    Remove-Item -Recurse -Force $RepoDir
}

New-Item -ItemType Directory -Force -Path $RuntimeRoot | Out-Null

if (-not (Test-Path (Join-Path $RepoDir ".git"))) {
    Write-Host "Cloning Xiaozhi backend..."
    git clone --filter=blob:none $Upstream $RepoDir
}

Write-Host "Fetching pinned revision..."
git -C $RepoDir fetch origin $PinnedCommit --depth 1
git -C $RepoDir checkout --detach $PinnedCommit

$ActualCommit = (git -C $RepoDir rev-parse HEAD).Trim()
if ($ActualCommit -ne $PinnedCommit) {
    throw "Pinned revision check failed. Expected $PinnedCommit, got $ActualCommit"
}

Write-Host "Pinned revision verified."

$Envs = (conda env list --json | ConvertFrom-Json).envs
$EnvExists = $false
foreach ($EnvPath in $Envs) {
    if ((Split-Path $EnvPath -Leaf) -eq $CondaEnv) {
        $EnvExists = $true
        break
    }
}

if (-not $EnvExists) {
    Write-Host "Creating Python 3.10 conda environment '$CondaEnv'..."
    conda create -n $CondaEnv python=3.10 -y
}

Write-Host "Installing native audio dependencies..."
conda install -n $CondaEnv -c conda-forge libopus ffmpeg -y

Write-Host "Installing Xiaozhi Python dependencies..."
conda run -n $CondaEnv python -m pip install --upgrade pip
conda run -n $CondaEnv python -m pip install -r (Join-Path $ServerDir "requirements.txt")

New-Item -ItemType Directory -Force -Path $DataDir | Out-Null

if (-not (Test-Path $ConfigTarget)) {
    Copy-Item $ConfigSource $ConfigTarget
    Write-Host "Created $ConfigTarget"
    Write-Host "Edit YOUR_WINDOWS_LAN_IP and API-key placeholders before starting the server."
} else {
    Write-Host "Existing .config.yaml preserved: $ConfigTarget"
}

Write-Host ""
Write-Host "Bootstrap complete."
Write-Host "Runtime: $RepoDir"
Write-Host "Server:  $ServerDir"
Write-Host "Config:  $ConfigTarget"
Write-Host ""
Write-Host "Next: edit .config.yaml, then run start_windows.ps1."
