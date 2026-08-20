param()

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

if ($env:OS -ne "Windows_NT") {
    throw "Kadence Control Surface is currently a Windows-only Alpha 2 operator UI."
}

$UiScript = Join-Path $PSScriptRoot "control_surface\KadenceControl.ps1"
if (-not (Test-Path $UiScript)) {
    throw "Kadence Control Surface script not found: $UiScript"
}

$WindowsPowerShell = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
if (-not (Test-Path $WindowsPowerShell)) {
    throw "Windows PowerShell was not found: $WindowsPowerShell"
}

# Run the WinForms host as a dedicated STA Windows PowerShell process, but keep
# it attached to this console. Alpha 2 intentionally favours visible diagnostics
# over a fire-and-forget launcher: if the UI fails during development, the real
# PowerShell exception must remain on screen instead of disappearing with a
# short-lived child window.
Write-Host "Starting Kadence Control Surface..."
& $WindowsPowerShell -STA -NoLogo -NoProfile -ExecutionPolicy Bypass -File $UiScript
$ExitCode = $LASTEXITCODE

if ($ExitCode -ne 0) {
    throw "Kadence Control Surface exited with code $ExitCode. See the error above."
}

Write-Host "Kadence Control Surface closed."
