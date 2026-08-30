param(
    [string]$RuntimeRoot = (Join-Path $PSScriptRoot ".runtime"),
    [string]$CondaEnv = "kadence2-xiaozhi",
    [string]$Model = "qwen3.5:4b",
    [bool]$PullIfMissing = $true,
    [int]$ContextLength = 8192
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$PersonaInjector = Join-Path $PSScriptRoot "apply_persona_windows.ps1"
$LocalStart = Join-Path $PSScriptRoot "start_local_windows.ps1"
$LocalStop = Join-Path $PSScriptRoot "stop_local_windows.ps1"
$LocalRuntimePatch = Join-Path $PSScriptRoot "apply_local_robot_runtime_windows.ps1"
$LocalProfileApplier = Join-Path $PSScriptRoot "apply_local_robot_profile_windows.ps1"
$M7Rollback = Join-Path $PSScriptRoot "remove_m7_behavior_windows.ps1"
$ToolsApplier = Join-Path $PSScriptRoot "apply_kadence_tools_windows.ps1"
$M6Applier = Join-Path $PSScriptRoot "apply_m6_utilities_windows.ps1"
$FrozenLauncher = Join-Path $PSScriptRoot "start_windows.ps1"
$LocalRuntimeRoot = Join-Path $RuntimeRoot "local"
$RetiredProfilePath = Join-Path $RuntimeRoot "kadence-llm-profile.txt"

function Enable-KadenceCondaPath {
    if (Get-Command conda -ErrorAction SilentlyContinue) {
        return
    }

    $Roots = New-Object System.Collections.Generic.List[string]
    if ($env:CONDA_EXE -and (Test-Path $env:CONDA_EXE)) {
        $CondaExeDir = Split-Path $env:CONDA_EXE -Parent
        if ((Split-Path $CondaExeDir -Leaf) -ieq "Scripts") {
            $Roots.Add((Split-Path $CondaExeDir -Parent))
        }
        else {
            $Roots.Add($CondaExeDir)
        }
    }

    foreach ($Root in @(
        (Join-Path $env:USERPROFILE "miniconda3"),
        (Join-Path $env:USERPROFILE "anaconda3"),
        (Join-Path $env:LOCALAPPDATA "miniconda3"),
        (Join-Path $env:LOCALAPPDATA "anaconda3"),
        (Join-Path $env:ProgramData "miniconda3"),
        (Join-Path $env:ProgramData "anaconda3")
    )) {
        if ($Root -and (-not $Roots.Contains($Root))) {
            $Roots.Add($Root)
        }
    }

    foreach ($Root in $Roots) {
        if (-not (Test-Path $Root)) {
            continue
        }

        $CondaBat = Join-Path $Root "condabin\conda.bat"
        $CondaExe = Join-Path $Root "Scripts\conda.exe"
        if ((-not (Test-Path $CondaBat)) -and (-not (Test-Path $CondaExe))) {
            continue
        }

        $PathParts = @(
            $Root,
            (Join-Path $Root "condabin"),
            (Join-Path $Root "Scripts"),
            (Join-Path $Root "Library\bin")
        ) | Where-Object { Test-Path $_ }

        $env:Path = (($PathParts + $env:Path) -join ";")
        if (Test-Path $CondaExe) {
            $env:CONDA_EXE = $CondaExe
        }

        if (Get-Command conda -ErrorAction SilentlyContinue) {
            Write-Host "Kadence Conda discovery: $Root"
            return
        }
    }

    throw "Conda was not found. Install Miniconda/Anaconda or set CONDA_EXE/KADENCE_HOME before starting Kadence."
}

foreach ($Required in @(
    $PersonaInjector,
    $LocalStart,
    $LocalStop,
    $LocalRuntimePatch,
    $LocalProfileApplier,
    $M7Rollback,
    $ToolsApplier,
    $M6Applier,
    $FrozenLauncher
)) {
    if (-not (Test-Path $Required)) {
        throw "Missing Alpha 3 M3A launcher dependency: $Required"
    }
}

$LocalStarted = $false
$PreviousToolMode = $env:KADENCE_TOOL_MODE
try {
    Write-Host "=== Kadence 2.0 Alpha 3 / M3A LOCAL robot ==="
    Write-Host "Loading canonical identity before server boot..."
    Write-Host ""

    & $PersonaInjector -RuntimeRoot $RuntimeRoot

    if (Test-Path $RetiredProfilePath) {
        Remove-Item $RetiredProfilePath -Force -ErrorAction SilentlyContinue
        Write-Host "Removed retired Gemini/Luna profile selector state."
    }

    Write-Host ""
    Write-Host "Ensuring M7 custom behaviour overlay is removed..."
    & $M7Rollback -RuntimeRoot $RuntimeRoot

    $env:KADENCE_TOOL_MODE = "m6_readonly"
    Write-Host ""
    Write-Host "Applying Kadence safe tool boundary: $env:KADENCE_TOOL_MODE"
    & $ToolsApplier -RuntimeRoot $RuntimeRoot
    & $M6Applier -RuntimeRoot $RuntimeRoot

    Enable-KadenceCondaPath

    Write-Host ""
    Write-Host "Starting Project-owned LOCAL cognition runtime..."
    & $LocalStart `
        -RuntimeRoot $LocalRuntimeRoot `
        -Model $Model `
        -PullIfMissing $PullIfMissing `
        -ContextLength $ContextLength
    $LocalStarted = $true

    Write-Host ""
    Write-Host "Applying LOCAL robot runtime compatibility..."
    & $LocalRuntimePatch -RuntimeRoot $RuntimeRoot

    Write-Host ""
    Write-Host "Applying explicit LOCAL robot cognition profile..."
    & $LocalProfileApplier -RuntimeRoot $RuntimeRoot -Model $Model

    Write-Host ""
    Write-Host "Starting frozen robot transport with LOCAL cognition..."
    Write-Host "Stop with Ctrl+C. LOCAL cleanup will run automatically."
    Write-Host ""

    & $FrozenLauncher `
        -RuntimeRoot $RuntimeRoot `
        -CondaEnv $CondaEnv `
        -ExpectedLlm "OllamaLLM"
}
finally {
    $env:KADENCE_TOOL_MODE = $PreviousToolMode
    if ($LocalStarted) {
        Write-Host ""
        Write-Host "Stopping Project-owned LOCAL cognition runtime..."
        & $LocalStop -RuntimeRoot $LocalRuntimeRoot
    }
}
