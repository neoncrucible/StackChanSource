param(
    [string]$RuntimeRoot = (Join-Path $PSScriptRoot ".runtime"),
    [string]$CondaEnv = "kadence2-xiaozhi",
    [ValidateRange(1,5)][int]$Repeats = 2,
    [ValidateRange(0,3)][int]$Warmup = 1
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$PersonaInjector = Join-Path $PSScriptRoot "apply_persona_windows.ps1"
$ProfileApplier = Join-Path $PSScriptRoot "apply_llm_profile_windows.ps1"
$ProfilePath = Join-Path $RuntimeRoot "kadence-llm-profile.txt"
$Runner = Join-Path $PSScriptRoot "benchmark\run_stage_b.py"
$PromptPack = Join-Path $PSScriptRoot "benchmark\m3_prompt_pack.json"
$Persona = Join-Path $PSScriptRoot "persona\KADENCE_CANONICAL.md"
$OutputRoot = Join-Path $RuntimeRoot "benchmarks\m3-stage-b"

foreach ($Required in @($PersonaInjector,$ProfileApplier,$Runner,$PromptPack,$Persona)) {
    if (-not (Test-Path $Required)) {
        throw "Required Milestone 3 benchmark file not found: $Required"
    }
}

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
        if (-not (Test-Path $Root)) { continue }
        $CondaBat = Join-Path $Root "condabin\conda.bat"
        $CondaExe = Join-Path $Root "Scripts\conda.exe"
        if ((-not (Test-Path $CondaBat)) -and (-not (Test-Path $CondaExe))) { continue }

        $PathParts = @(
            $Root,
            (Join-Path $Root "condabin"),
            (Join-Path $Root "Scripts"),
            (Join-Path $Root "Library\bin")
        ) | Where-Object { Test-Path $_ }
        $env:Path = (($PathParts + $env:Path) -join ";")
        if (Test-Path $CondaExe) { $env:CONDA_EXE = $CondaExe }

        if (Get-Command conda -ErrorAction SilentlyContinue) {
            Write-Host "Kadence Conda discovery: $Root"
            return
        }
    }

    throw "Conda was not found. Install Miniconda/Anaconda or set CONDA_EXE before running the benchmark."
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
    throw "Conda environment '$EnvironmentName' was not found."
}

function Assert-KadenceServerStopped {
    $Conflicts = New-Object System.Collections.Generic.List[string]

    $Udp = Get-NetUDPEndpoint -LocalPort 45872 -ErrorAction SilentlyContinue
    foreach ($Entry in @($Udp)) {
        if ($null -ne $Entry) {
            $Conflicts.Add("UDP 45872 (PID $($Entry.OwningProcess))")
        }
    }

    foreach ($Port in @(8000,8003)) {
        $Tcp = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue
        foreach ($Entry in @($Tcp)) {
            if ($null -ne $Entry) {
                $Conflicts.Add("TCP $Port (PID $($Entry.OwningProcess))")
            }
        }
    }

    if ($Conflicts.Count -gt 0) {
        throw "Stop the Kadence server before Stage B. Busy endpoint(s): $($Conflicts -join ', ')"
    }
}

function Get-SavedProfile {
    if (-not (Test-Path $ProfilePath)) {
        return "gemini"
    }
    $Candidate = ([System.IO.File]::ReadAllText($ProfilePath)).Trim().ToLowerInvariant()
    if ($Candidate -notin @("gemini","luna")) {
        throw "Unsupported saved LLM profile '$Candidate'."
    }
    return $Candidate
}

Write-Host "=== Kadence 2.0 Alpha 2 / Milestone 3 Stage B ==="
Write-Host "Controlled provider benchmark: Gemini 3.5 Flash-Lite vs GPT-5.6 Luna"
Write-Host "No robot audio or transport tuning is involved."
Write-Host ""

Assert-KadenceServerStopped
Enable-KadenceCondaPath
$CondaPrefix = Resolve-CondaEnvPrefix -EnvironmentName $CondaEnv
$PythonExe = Join-Path $CondaPrefix "python.exe"
if (-not (Test-Path $PythonExe)) {
    throw "Python was not found in Conda environment '$CondaEnv': $PythonExe"
}

$SavedProfile = Get-SavedProfile
$BenchmarkExitCode = 1

try {
    # Repair/verify the local runtime and canonical identity first. This invokes
    # only the existing guarded Alpha 2/Alpha 1 runtime patches; it does not
    # start the server or touch firmware/transport configuration.
    & $PersonaInjector -RuntimeRoot $RuntimeRoot

    # Ensure the Luna config block and reasoning compatibility patch exist for
    # direct provider instantiation. The user's saved pre-boot selection is
    # restored in the finally block even if the benchmark fails.
    & $ProfileApplier -Profile "luna" -RuntimeRoot $RuntimeRoot

    New-Item -ItemType Directory -Force -Path $OutputRoot | Out-Null
    $env:PYTHONUTF8 = "1"
    $env:PYTHONIOENCODING = "utf-8"

    Write-Host ""
    Write-Host "Running $Repeats measured repeat(s) per prompt with $Warmup warm-up request(s) per provider..."
    Write-Host ""

    & $PythonExe $Runner `
        --runtime-root $RuntimeRoot `
        --output-root $OutputRoot `
        --prompt-pack $PromptPack `
        --persona $Persona `
        --repeats $Repeats `
        --warmup $Warmup

    $BenchmarkExitCode = $LASTEXITCODE
    if ($BenchmarkExitCode -ne 0) {
        throw "Milestone 3 Stage B benchmark exited with code $BenchmarkExitCode."
    }
}
finally {
    try {
        & $ProfileApplier -Profile $SavedProfile -RuntimeRoot $RuntimeRoot
        Write-Host "Restored saved pre-boot LLM profile: $SavedProfile"
    }
    catch {
        Write-Warning ("Could not restore saved LLM profile: " + $_.Exception.Message)
    }
}

Write-Host ""
Write-Host "Stage B complete. Results are local-only under:"
Write-Host $OutputRoot
Write-Host "Open the newest blind_review.md first; do not open blind_mapping.json until quality judging is finished."
