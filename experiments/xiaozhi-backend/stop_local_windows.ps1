param(
    [string]$RuntimeRoot = (Join-Path $PSScriptRoot ".runtime\local")
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

if ($env:OS -ne "Windows_NT") {
    throw "Kadence LOCAL runtime is currently Windows-only."
}

. (Join-Path $PSScriptRoot "kadence_local_common.ps1")

$Paths = Get-KadenceLocalPaths -RuntimeRoot $RuntimeRoot
$Owners = @(Get-KadencePortOwners -Port 11434)

if (-not (Test-Path $Paths.PidPath) -or -not (Test-Path $Paths.StatePath)) {
    if ($Owners.Count -eq 0) {
        Write-Host "Kadence LOCAL runtime is already stopped."
        return
    }
    throw "TCP 11434 is in use but no Kadence LOCAL ownership state exists. Refusing to stop an unknown process."
}

$State = Get-Content $Paths.StatePath -Raw | ConvertFrom-Json
$ProcessId = [int]$State.pid
$null = Assert-KadenceOwnedOllamaProcess -ProcessId $ProcessId -ExpectedExecutable ([string]$State.executable)

if ($Owners -notcontains $ProcessId) {
    throw "Recorded Kadence LOCAL PID $ProcessId does not own TCP 11434. Refusing destructive cleanup."
}

if (Test-KadenceOllamaApi) {
    try {
        $UnloadBody = [ordered]@{
            model = [string]$State.model
            prompt = ""
            stream = $false
            keep_alive = 0
        }
        $null = Invoke-KadenceOllamaApi -Method Post -Path "generate" -Body $UnloadBody -TimeoutSec 30
    }
    catch {
        Write-Warning "LOCAL model unload request failed; process-tree shutdown will continue: $($_.Exception.Message)"
    }
}

Write-Host "Stopping Kadence LOCAL PID $ProcessId..."
$TaskkillPath = Join-Path $env:SystemRoot "System32\taskkill.exe"
$KillProcess = Start-Process -FilePath $TaskkillPath `
    -ArgumentList @("/PID", [string]$ProcessId, "/T", "/F") `
    -WindowStyle Hidden -Wait -PassThru
$KillExitCode = $KillProcess.ExitCode

$StillThere = Get-KadenceProcessInfo -ProcessId $ProcessId
if ($null -ne $StillThere) {
    throw "Failed to stop Kadence LOCAL PID $ProcessId (taskkill exit code $KillExitCode)."
}
if ($KillExitCode -ne 0) {
    Write-Warning "taskkill returned exit code $KillExitCode after Kadence LOCAL PID $ProcessId exited; continuing to explicit port verification."
}

$PortReleased = $false
for ($Attempt = 0; $Attempt -lt 40; $Attempt++) {
    Start-Sleep -Milliseconds 100
    if (@(Get-KadencePortOwners -Port 11434).Count -eq 0) {
        $PortReleased = $true
        break
    }
}
if (-not $PortReleased) {
    throw "Kadence LOCAL process ended but TCP 11434 is still occupied. Refusing to pretend shutdown is clean."
}

Remove-Item $Paths.PidPath, $Paths.StatePath -Force -ErrorAction SilentlyContinue
Write-Host "Kadence LOCAL stopped cleanly; TCP 11434 released."
