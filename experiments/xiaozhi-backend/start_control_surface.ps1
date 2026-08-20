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

$Arguments = "-STA -NoLogo -NoProfile -ExecutionPolicy Bypass -File `"$UiScript`""
Start-Process -FilePath $WindowsPowerShell -ArgumentList $Arguments | Out-Null

Write-Host "Kadence Control Surface launched."
