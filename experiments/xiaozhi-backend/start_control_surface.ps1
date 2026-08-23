param()

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

if ($env:OS -ne "Windows_NT") {
    throw "Kadence Control Surface is currently a Windows-only Alpha 2 operator UI."
}

$UiScript = Join-Path $PSScriptRoot "control_surface\KadenceControlV3.ps1"
$PatchScript = Join-Path $PSScriptRoot "control_surface\KadenceControlPatchV4.ps1"
$PatchScriptV41 = Join-Path $PSScriptRoot "control_surface\KadenceControlPatchV41.ps1"
$PatchScriptV43 = Join-Path $PSScriptRoot "control_surface\KadenceControlPatchV43.ps1"
$EyeFixPatch = Join-Path $PSScriptRoot "control_surface\KadenceControlPatchEyeFix.ps1"
$RetiredProfilePath = Join-Path $PSScriptRoot ".runtime\kadence-llm-profile.txt"

foreach ($Required in @($UiScript, $PatchScript, $PatchScriptV41, $PatchScriptV43, $EyeFixPatch)) {
    if (-not (Test-Path $Required)) {
        throw "Kadence Control Surface dependency not found: $Required"
    }
}

if (Test-Path $RetiredProfilePath) {
    Remove-Item $RetiredProfilePath -Force -ErrorAction SilentlyContinue
}

$WindowsPowerShell = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
if (-not (Test-Path $WindowsPowerShell)) {
    throw "Windows PowerShell was not found: $WindowsPowerShell"
}

# Restore the accepted M6 operator surface: V4 + V4.1 + Luna-only V4.3.
# Apply only the later EYE geometry repair; no M7 DEFAULT/CUSTOM controls are
# rendered and no behaviour-control port is added to the UI/preflight.
$TempUi = Join-Path (Split-Path $UiScript -Parent) ("KadenceControl-run-{0}.ps1" -f [guid]::NewGuid().ToString("N"))
$Utf8Bom = New-Object System.Text.UTF8Encoding($true)
$UiText = [System.IO.File]::ReadAllText($UiScript, [System.Text.Encoding]::UTF8)
$UiText = & $PatchScript -UiText $UiText
$UiText = & $PatchScriptV41 -UiText $UiText
$UiText = & $PatchScriptV43 -UiText $UiText
$UiText = & $EyeFixPatch -UiText $UiText
[System.IO.File]::WriteAllText($TempUi, $UiText, $Utf8Bom)

Write-Host "Starting Kadence Control Surface V4.3 / M6 + EYE fix..."
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
