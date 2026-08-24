param(
    [string]$RuntimeRoot = (Join-Path $PSScriptRoot ".runtime\local"),
    [string]$Model = "qwen3.5:4b"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$StartScript = Join-Path $PSScriptRoot "start_local_windows.ps1"
$StopScript = Join-Path $PSScriptRoot "stop_local_windows.ps1"
$InvokeScript = Join-Path $PSScriptRoot "invoke_local_windows.ps1"

foreach ($Required in @($StartScript, $StopScript, $InvokeScript)) {
    if (-not (Test-Path $Required)) {
        throw "Missing Alpha 3 LOCAL test dependency: $Required"
    }
}

$Results = New-Object System.Collections.Generic.List[object]
$Started = $false

function Assert-PortReleased {
    $Busy = @(Get-NetTCPConnection -State Listen -LocalPort 11434 -ErrorAction SilentlyContinue)
    if ($Busy.Count -ne 0) {
        throw "TCP 11434 remained occupied after LOCAL shutdown."
    }
}

try {
    Write-Host "=== Alpha 3 LOCAL standalone validation ==="
    Write-Host "Candidate: $Model"
    Write-Host "No Xiaozhi server, robot transport or firmware is started by this test."
    Write-Host ""

    & $StartScript -RuntimeRoot $RuntimeRoot -Model $Model -PullIfMissing $true
    $Started = $true

    $Factual = & $InvokeScript -RuntimeRoot $RuntimeRoot `
        -Prompt "What is the capital of Norway? Answer in one sentence."
    $Results.Add($Factual)

    $Personality = & $InvokeScript -RuntimeRoot $RuntimeRoot `
        -Prompt "I have just spent twenty minutes debugging a problem that turned out to be a loose USB cable. What do you say?"
    $Results.Add($Personality)

    & $StopScript -RuntimeRoot $RuntimeRoot
    $Started = $false
    Assert-PortReleased

    Write-Host ""
    Write-Host "--- restart gate ---"
    & $StartScript -RuntimeRoot $RuntimeRoot -Model $Model -PullIfMissing $false
    $Started = $true

    $Restart = & $InvokeScript -RuntimeRoot $RuntimeRoot `
        -Prompt "In one sentence, what does a DNS A record do?"
    $Results.Add($Restart)

    & $StopScript -RuntimeRoot $RuntimeRoot
    $Started = $false
    Assert-PortReleased

    Write-Host ""
    Write-Host "=== LOCAL standalone gates completed ==="
    Write-Host "START -> factual -> personality -> STOP -> RESTART -> prompt -> STOP all completed without a leaked listener."
    Write-Host ""
    $Results | Format-Table Model,WallMilliseconds,LoadMilliseconds,PromptTokens,EvalTokens,TokensPerSecond -AutoSize
}
finally {
    if ($Started) {
        try { & $StopScript -RuntimeRoot $RuntimeRoot } catch { Write-Warning $_.Exception.Message }
    }
}
