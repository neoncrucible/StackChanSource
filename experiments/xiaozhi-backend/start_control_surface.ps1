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

# Windows PowerShell 5.1 treats UTF-8 text without a BOM as the active ANSI
# code page. The tracked UI is UTF-8 and contains a few display-only Unicode
# characters, so launching it directly can corrupt those bytes before parsing.
# Make a temporary UTF-8-with-BOM execution copy IN THE SAME DIRECTORY as the
# tracked UI. This matters because KadenceControl.ps1 intentionally resolves
# the backend root relative to $PSScriptRoot. A temp copy under %TEMP% changes
# $PSScriptRoot and makes it look for start_alpha2_windows.ps1 in AppData.
# The tracked source remains unchanged and the runtime copy is deleted on exit.
$UiDir = Split-Path $UiScript -Parent
$TempUi = Join-Path $UiDir (".KadenceControl.runtime-{0}.ps1" -f [guid]::NewGuid().ToString("N"))
$Utf8Bom = New-Object System.Text.UTF8Encoding($true)
$UiText = [System.IO.File]::ReadAllText($UiScript, [System.Text.Encoding]::UTF8)
[System.IO.File]::WriteAllText($TempUi, $UiText, $Utf8Bom)

Write-Host "Starting Kadence Control Surface..."
try {
    & $WindowsPowerShell -STA -NoLogo -NoProfile -ExecutionPolicy Bypass -File $TempUi
    $ExitCode = $LASTEXITCODE
}
finally {
    Remove-Item $TempUi -Force -ErrorAction SilentlyContinue
}

if ($ExitCode -ne 0) {
    throw "Kadence Control Surface exited with code $ExitCode. See the error above."
}

Write-Host "Kadence Control Surface closed."
