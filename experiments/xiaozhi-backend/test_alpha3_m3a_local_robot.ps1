param()

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = $PSScriptRoot
$Profile = Join-Path $Root "apply_local_robot_profile_windows.ps1"
$Launcher = Join-Path $Root "start_alpha3_local_robot_windows.ps1"
$FrozenLauncher = Join-Path $Root "start_windows.ps1"
$LocalCommon = Join-Path $Root "kadence_local_common.ps1"
$LocalStop = Join-Path $Root "stop_local_windows.ps1"

foreach ($Path in @($Profile, $Launcher, $FrozenLauncher, $LocalCommon, $LocalStop)) {
    if (-not (Test-Path $Path)) {
        throw "FAIL missing Alpha 3 M3A dependency: $Path"
    }
}

Write-Host "=== Alpha 3 M3A LOCAL robot static gate ==="

function Assert-PowerShellParses {
    param([Parameter(Mandatory = $true)][string]$Path)

    $Tokens = $null
    $ParseErrors = $null
    $null = [System.Management.Automation.Language.Parser]::ParseFile(
        $Path,
        [ref]$Tokens,
        [ref]$ParseErrors
    )
    if (@($ParseErrors).Count -gt 0) {
        $Details = @($ParseErrors | ForEach-Object {
            "line $($_.Extent.StartLineNumber): $($_.Message)"
        }) -join "`r`n"
        throw "FAIL PowerShell parse errors in ${Path}:`r`n$Details"
    }
}

foreach ($Path in @($Profile, $Launcher, $FrozenLauncher, $LocalCommon, $LocalStop)) {
    Assert-PowerShellParses -Path $Path
}

$ProfileText = [System.IO.File]::ReadAllText($Profile, [System.Text.Encoding]::UTF8)
foreach ($Marker in @(
    'Get-KadenceCanonicalPersona',
    'Assert-KadenceOwnedOllamaProcess',
    'Get-KadencePortOwners -Port 11434',
    'Test-KadenceOllamaApi',
    'LLM: OllamaLLM',
    'type: ollama',
    'model_name: "$Model"',
    'http://127.0.0.1:11434',
    'No LUNA cognition fallback is configured for this startup path.'
)) {
    if (-not $ProfileText.Contains($Marker)) {
        throw "FAIL LOCAL robot profile missing guard marker: $Marker"
    }
}

$LauncherText = [System.IO.File]::ReadAllText($Launcher, [System.Text.Encoding]::UTF8)
foreach ($Marker in @(
    'apply_persona_windows.ps1',
    'start_local_windows.ps1',
    'stop_local_windows.ps1',
    'apply_local_robot_profile_windows.ps1',
    'remove_m7_behavior_windows.ps1',
    'apply_kadence_tools_windows.ps1',
    'apply_m6_utilities_windows.ps1',
    '$env:KADENCE_TOOL_MODE = "m6_readonly"',
    '$LocalStarted = $true',
    '-ExpectedLlm "OllamaLLM"',
    '& $LocalStop -RuntimeRoot $LocalRuntimeRoot'
)) {
    if (-not $LauncherText.Contains($Marker)) {
        throw "FAIL M3A launcher missing lifecycle marker: $Marker"
    }
}
foreach ($Forbidden in @(
    'apply_luna_profile_windows.ps1',
    '-ExpectedLlm "OpenAILLM"',
    'AUTO'
)) {
    if ($LauncherText.Contains($Forbidden)) {
        throw "FAIL M3A launcher contains forbidden routing marker: $Forbidden"
    }
}

$FrozenText = [System.IO.File]::ReadAllText($FrozenLauncher, [System.Text.Encoding]::UTF8)
foreach ($Marker in @(
    '[ValidateSet("OpenAILLM","OllamaLLM")]',
    '[string]$ExpectedLlm = "OpenAILLM"',
    '''(?m)^  LLM:[ \t]+(?<name>\S+)[ \t]*\r?$''',
    'selected_module LLM preflight',
    'does not match required provider',
    'Kadence cognition preflight: selected_module.LLM='
)) {
    if (-not $FrozenText.Contains($Marker)) {
        throw "FAIL frozen transport launcher missing provider guard marker: $Marker"
    }
}

$SelectionPattern = '(?m)^  LLM:[ \t]+(?<name>\S+)[ \t]*\r?$'
$CrLfFixture = "selected_module:`r`n  LLM: OllamaLLM`r`nTTS:`r`n"
$FixtureMatches = [regex]::Matches($CrLfFixture, $SelectionPattern)
if ($FixtureMatches.Count -ne 1 -or
    $FixtureMatches[0].Groups['name'].Value -ne "OllamaLLM") {
    throw "FAIL selected_module LLM preflight does not handle Windows CRLF config text."
}

$CommonText = [System.IO.File]::ReadAllText($LocalCommon, [System.Text.Encoding]::UTF8)
foreach ($Marker in @(
    '$PathVisible = -not [string]::IsNullOrWhiteSpace($ExecutablePath)',
    '$CommandVisible = -not [string]::IsNullOrWhiteSpace($CommandLine)',
    '$MetadataComplete = $PathVisible -and $CommandVisible',
    'caller must corroborate ownership with recorded start time, TCP 11434 and the Ollama API'
)) {
    if (-not $CommonText.Contains($Marker)) {
        throw "FAIL LOCAL ownership helper missing blank-CIM guard marker: $Marker"
    }
}

$StopText = [System.IO.File]::ReadAllText($LocalStop, [System.Text.Encoding]::UTF8)
foreach ($Marker in @(
    '$Owners -notcontains $ProcessId',
    '$LiveProcess.StartTime.ToUniversalTime()',
    '$ActualStartedUtc -gt $RecordedStartedUtc.AddSeconds(5)',
    'Invoke-KadenceOllamaApi -Method Get -Path "ps"',
    '$RunningModels -notcontains ([string]$State.model)'
)) {
    if (-not $StopText.Contains($Marker)) {
        throw "FAIL LOCAL stop script missing corroborated-ownership marker: $Marker"
    }
}

$RepoRoot = (Resolve-Path (Join-Path $Root "..\..")).Path
$FirmwareDelta = @(git -C $RepoRoot diff --name-only c74d8949f33c6dea1d7df2bea248cad9e82d5dd1..HEAD -- firmware)
if ($LASTEXITCODE -ne 0) {
    throw "FAIL git firmware provenance check could not run."
}
if ($FirmwareDelta.Count -ne 0) {
    throw "FAIL Alpha 3 branch contains committed firmware changes:`r`n$($FirmwareDelta -join "`r`n")"
}

Write-Host "PASS bundled Ollama provider selected through existing provider boundary"
Write-Host "PASS Project-owned Ollama process and TCP 11434 ownership guards"
Write-Host "PASS blank Windows CIM metadata requires start-time/API/model corroboration"
Write-Host "PASS canonical persona v2 guard"
Write-Host "PASS frozen robot transport launcher requires explicit expected provider"
Write-Host "PASS provider preflight handles Windows CRLF runtime YAML"
Write-Host "PASS LOCAL startup fails closed instead of selecting OpenAILLM"
Write-Host "PASS accepted M6 safe tool boundary retained"
Write-Host "PASS LOCAL cleanup is wired through finally"
Write-Host "PASS no AUTO routing and no LUNA profile application"
Write-Host "PASS no committed firmware delta from frozen Alpha 2 closure"
Write-Host "PASS PowerShell sources parse cleanly"
Write-Host ""
Write-Host "STATIC GATE COMPLETE - real StackChan voice behaviour is not yet validated."
