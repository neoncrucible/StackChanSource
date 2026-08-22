param(
    [string]$RuntimeRoot = (Join-Path $PSScriptRoot ".runtime"),
    [string]$CondaEnv = "kadence2-xiaozhi"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$PersonaInjector = Join-Path $PSScriptRoot "apply_persona_windows.ps1"
$LunaProfileApplier = Join-Path $PSScriptRoot "apply_luna_profile_windows.ps1"
$ToolsApplier = Join-Path $PSScriptRoot "apply_kadence_tools_windows.ps1"
$M6Applier = Join-Path $PSScriptRoot "apply_m6_utilities_windows.ps1"
$FrozenLauncher = Join-Path $PSScriptRoot "start_windows.ps1"
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
        } else {
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
    $LunaProfileApplier,
    $ToolsApplier,
    $M6Applier,
    $FrozenLauncher
)) {
    if (-not (Test-Path $Required)) {
        throw "Missing Alpha 2 launcher dependency: $Required"
    }
}

Write-Host "=== Kadence 2.0 Alpha 2 ==="
Write-Host "Loading canonical identity before server boot..."
Write-Host ""

& $PersonaInjector -RuntimeRoot $RuntimeRoot

# M3 proved the abstraction; M5 proved the tool boundary. From M6 onward Alpha 2
# deliberately carries one cloud cognition path: Luna. LOCAL/LUNA selection is
# the target beta/live architecture and is not smuggled into Alpha 2 early.
if (Test-Path $RetiredProfilePath) {
    Remove-Item $RetiredProfilePath -Force -ErrorAction SilentlyContinue
    Write-Host "Removed retired Gemini/Luna profile selector state."
}
Write-Host ""
Write-Host "Applying fixed Alpha 2 LLM profile: luna"
& $LunaProfileApplier -RuntimeRoot $RuntimeRoot

# M5 remains the authority boundary. M6 swaps the inert probe advertisement for
# exactly three read-only Project-owned utilities; no generic HTTP/MCP/OS tool is
# exposed to Luna.
$env:KADENCE_TOOL_MODE = "m6_readonly"
Write-Host ""
Write-Host "Applying Kadence safe tool boundary: $env:KADENCE_TOOL_MODE"
& $ToolsApplier -RuntimeRoot $RuntimeRoot
& $M6Applier -RuntimeRoot $RuntimeRoot

Write-Host ""
Write-Host "Canonical identity ready. Preparing local runtime..."
Enable-KadenceCondaPath
Write-Host "Starting frozen Alpha 1 transport stack..."
Write-Host ""

& $FrozenLauncher -RuntimeRoot $RuntimeRoot -CondaEnv $CondaEnv
