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
$Requirements = Join-Path $ServerDir "requirements.txt"
$ConfigSource = Join-Path $PSScriptRoot "kadence.config.example.yaml"
$ConfigTarget = Join-Path $DataDir ".config.yaml"

function Require-Command([string]$Name) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required command '$Name' was not found in PATH."
    }
}

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [Parameter(Mandatory = $true)][string]$FailureMessage
    )

    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$FailureMessage (exit code $LASTEXITCODE)"
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
    Invoke-Checked -FilePath "git" -Arguments @(
        "clone", "--filter=blob:none", $Upstream, $RepoDir
    ) -FailureMessage "Failed to clone the pinned Xiaozhi backend repository"
}

Write-Host "Fetching pinned revision..."
Invoke-Checked -FilePath "git" -Arguments @(
    "-C", $RepoDir, "fetch", "--depth", "1", "origin", $PinnedCommit
) -FailureMessage "Failed to fetch the pinned Xiaozhi backend revision"

Invoke-Checked -FilePath "git" -Arguments @(
    "-C", $RepoDir, "checkout", "--detach", $PinnedCommit
) -FailureMessage "Failed to check out the pinned Xiaozhi backend revision"

$ActualCommit = (& git -C $RepoDir rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0) {
    throw "Failed to read the Xiaozhi runtime revision."
}
if ($ActualCommit -ne $PinnedCommit) {
    throw "Pinned revision check failed. Expected $PinnedCommit, got $ActualCommit"
}

Write-Host "Pinned revision verified."

$CondaEnvJson = & conda env list --json
if ($LASTEXITCODE -ne 0) {
    throw "Failed to list conda environments."
}
$Envs = ($CondaEnvJson | ConvertFrom-Json).envs
$EnvExists = $false
foreach ($EnvPath in $Envs) {
    if ((Split-Path $EnvPath -Leaf) -eq $CondaEnv) {
        $EnvExists = $true
        break
    }
}

if (-not $EnvExists) {
    Write-Host "Creating Python 3.10 conda environment '$CondaEnv'..."
    Invoke-Checked -FilePath "conda" -Arguments @(
        "create", "-n", $CondaEnv, "python=3.10", "-y"
    ) -FailureMessage "Failed to create the Kadence 2.0 conda environment"
}

Write-Host "Installing native audio dependencies..."
Invoke-Checked -FilePath "conda" -Arguments @(
    "install", "-n", $CondaEnv, "-c", "conda-forge", "libopus", "ffmpeg", "-y"
) -FailureMessage "Failed to install libopus/ffmpeg"

Write-Host "Installing Xiaozhi Python dependencies..."
Invoke-Checked -FilePath "conda" -Arguments @(
    "run", "-n", $CondaEnv, "python", "-m", "pip", "install", "--upgrade", "pip"
) -FailureMessage "Failed to upgrade pip in the Kadence 2.0 environment"

Invoke-Checked -FilePath "conda" -Arguments @(
    "run", "-n", $CondaEnv, "python", "-m", "pip", "install", "-r", $Requirements
) -FailureMessage "Failed to install Xiaozhi Python requirements"

New-Item -ItemType Directory -Force -Path $DataDir | Out-Null

if (-not (Test-Path $ConfigTarget)) {
    Copy-Item $ConfigSource $ConfigTarget
    Write-Host "Created local Alpha config: $ConfigTarget"
    Write-Host "API keys will be requested securely by start_windows.ps1 on first launch."
} else {
    Write-Host "Existing .config.yaml preserved: $ConfigTarget"
}

Write-Host ""
Write-Host "Bootstrap complete."
Write-Host "Runtime: $RepoDir"
Write-Host "Server:  $ServerDir"
Write-Host "Config:  $ConfigTarget"
Write-Host ""
Write-Host "Next: run start_windows.ps1."
