param(
    [string]$RuntimeRoot = (Join-Path $PSScriptRoot ".runtime"),
    [string]$CondaEnv = "kadence2-xiaozhi",
    [string]$LlmProfile = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$PersonaInjector = Join-Path $PSScriptRoot "apply_persona_windows.ps1"
$LlmProfileApplier = Join-Path $PSScriptRoot "apply_llm_profile_windows.ps1"
$FrozenLauncher = Join-Path $PSScriptRoot "start_windows.ps1"
$LocalProfilePath = Join-Path $RuntimeRoot "kadence-llm-profile.txt"

function Enable-KadenceCondaPath {
    # The packaged Control Surface starts from a clean Windows process and may
    # not inherit the user's interactive shell PATH. Discover common Miniconda/
    # Anaconda installs and expose conda to the frozen Alpha 1 launcher without
    # modifying that launcher or any transport behaviour.
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

function Resolve-KadenceLlmProfile {
    if (-not [string]::IsNullOrWhiteSpace($LlmProfile)) {
        $Candidate = $LlmProfile.Trim().ToLowerInvariant()
    }
    elseif (-not [string]::IsNullOrWhiteSpace($env:KADENCE_LLM_PROFILE)) {
        $Candidate = $env:KADENCE_LLM_PROFILE.Trim().ToLowerInvariant()
    }
    elseif (Test-Path $LocalProfilePath) {
        $Candidate = ([System.IO.File]::ReadAllText($LocalProfilePath)).Trim().ToLowerInvariant()
    }
    else {
        $Candidate = "gemini"
    }

    if ($Candidate -notin @("gemini", "luna")) {
        throw "Unsupported Kadence LLM profile '$Candidate'. Expected gemini or luna."
    }

    return $Candidate
}

if (-not (Test-Path $PersonaInjector)) {
    throw "Missing Alpha 2 persona injector: $PersonaInjector"
}
if (-not (Test-Path $LlmProfileApplier)) {
    throw "Missing Alpha 2 LLM profile applier: $LlmProfileApplier"
}
if (-not (Test-Path $FrozenLauncher)) {
    throw "Missing frozen Alpha 1 launcher: $FrozenLauncher"
}

Write-Host "=== Kadence 2.0 Alpha 2 ==="
Write-Host "Loading canonical identity before server boot..."
Write-Host ""

& $PersonaInjector -RuntimeRoot $RuntimeRoot

$ResolvedLlmProfile = Resolve-KadenceLlmProfile
Write-Host ""
Write-Host "Applying pre-boot LLM profile: $ResolvedLlmProfile"
& $LlmProfileApplier -Profile $ResolvedLlmProfile -RuntimeRoot $RuntimeRoot

Write-Host ""
Write-Host "Canonical identity ready. Preparing local runtime..."
Enable-KadenceCondaPath
Write-Host "Starting frozen Alpha 1 transport stack..."
Write-Host ""

# Deliberately delegate transport startup to the proven Alpha 1 launcher.
# Alpha 2 owns identity/runtime/LLM-profile selection around it; it does not fork
# or retune the frozen transport. LLM selection is fixed for the server run and
# changing it requires shutdown/restart.
& $FrozenLauncher -RuntimeRoot $RuntimeRoot -CondaEnv $CondaEnv
