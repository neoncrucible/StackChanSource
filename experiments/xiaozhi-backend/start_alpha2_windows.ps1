param(
    [string]$RuntimeRoot = (Join-Path $PSScriptRoot ".runtime"),
    [string]$CondaEnv = "kadence2-xiaozhi"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$PersonaInjector = Join-Path $PSScriptRoot "apply_persona_windows.ps1"
$FrozenLauncher = Join-Path $PSScriptRoot "start_windows.ps1"

if (-not (Test-Path $PersonaInjector)) {
    throw "Missing Alpha 2 persona injector: $PersonaInjector"
}
if (-not (Test-Path $FrozenLauncher)) {
    throw "Missing frozen Alpha 1 launcher: $FrozenLauncher"
}

Write-Host "=== Kadence 2.0 Alpha 2 ==="
Write-Host "Loading canonical identity before server boot..."
Write-Host ""

& $PersonaInjector -RuntimeRoot $RuntimeRoot

Write-Host ""
Write-Host "Canonical identity ready. Starting frozen Alpha 1 transport stack..."
Write-Host ""

# Deliberately delegate transport startup to the proven Alpha 1 launcher.
# Alpha 2 owns identity around it; it does not fork or retune that transport.
& $FrozenLauncher -RuntimeRoot $RuntimeRoot -CondaEnv $CondaEnv
