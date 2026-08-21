param()

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

if ($env:OS -ne "Windows_NT") {
    throw "Kadence Control Surface is currently a Windows-only Alpha 2 operator UI."
}

$UiScript = Join-Path $PSScriptRoot "control_surface\KadenceControlV3.ps1"
$PatchScript = Join-Path $PSScriptRoot "control_surface\KadenceControlPatchV4.ps1"

if (-not (Test-Path $UiScript)) {
    throw "Kadence Control Surface script not found: $UiScript"
}
if (-not (Test-Path $PatchScript)) {
    throw "Kadence Control Surface V4 patch not found: $PatchScript"
}

$WindowsPowerShell = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
if (-not (Test-Path $WindowsPowerShell)) {
    throw "Windows PowerShell was not found: $WindowsPowerShell"
}

# Keep the validated V3 source intact and render the current Alpha 2 operator UI
# into a temporary UTF-8-BOM sibling copy. This preserves PSScriptRoot and avoids
# Windows PowerShell 5.1 ANSI parsing problems.
$TempUi = Join-Path (Split-Path $UiScript -Parent) ("KadenceControl-run-{0}.ps1" -f [guid]::NewGuid().ToString("N"))
$Utf8Bom = New-Object System.Text.UTF8Encoding($true)
$UiText = [System.IO.File]::ReadAllText($UiScript, [System.Text.Encoding]::UTF8)
$UiText = & $PatchScript -UiText $UiText
[System.IO.File]::WriteAllText($TempUi, $UiText, $Utf8Bom)

Write-Host "Starting Kadence Control Surface V4..."
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
