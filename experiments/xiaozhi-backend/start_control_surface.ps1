param()

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

if ($env:OS -ne "Windows_NT") {
    throw "Kadence Control Surface is currently Windows-only."
}

$UiScript = Join-Path $PSScriptRoot "control_surface\KadenceControlV3.ps1"
$PatchScript = Join-Path $PSScriptRoot "control_surface\KadenceControlPatchV4.ps1"
$PatchScriptV41 = Join-Path $PSScriptRoot "control_surface\KadenceControlPatchV41.ps1"
$PatchScriptV43 = Join-Path $PSScriptRoot "control_surface\KadenceControlPatchV43.ps1"
$EyeFixPatch = Join-Path $PSScriptRoot "control_surface\KadenceControlPatchEyeFix.ps1"
$Alpha3EnginePatch = Join-Path $PSScriptRoot "control_surface\KadenceControlPatchAlpha3Engine.ps1"
$Alpha3EnginePatchRunner = Join-Path $PSScriptRoot "control_surface\InvokeKadenceControlPatchAlpha3Engine.ps1"
$QuietChatPatch = Join-Path $PSScriptRoot "control_surface\KadenceControlPatchAlpha3QuietChat.ps1"
$RetiredProfilePath = Join-Path $PSScriptRoot ".runtime\kadence-llm-profile.txt"

foreach ($Required in @($UiScript, $PatchScript, $PatchScriptV41, $PatchScriptV43, $EyeFixPatch, $Alpha3EnginePatch, $Alpha3EnginePatchRunner, $QuietChatPatch)) {
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

# Preserve the physically accepted M6 operator surface and EYE geometry, then
# apply the Alpha 3-only engine/chat overlay. Retired M7 DEFAULT/CUSTOM controls
# remain excluded and there is no automatic engine-routing mode.
$TempUi = Join-Path (Split-Path $UiScript -Parent) ("KadenceControl-run-{0}.ps1" -f [guid]::NewGuid().ToString("N"))
$Utf8Bom = New-Object System.Text.UTF8Encoding($true)
$UiText = [System.IO.File]::ReadAllText($UiScript, [System.Text.Encoding]::UTF8)
$UiText = & $PatchScript -UiText $UiText
$UiText = & $PatchScriptV41 -UiText $UiText
$UiText = & $PatchScriptV43 -UiText $UiText
$UiText = & $EyeFixPatch -UiText $UiText

# Older accepted Control Surface files may retain LF while newly pulled Alpha 3
# patch files are checked out as CRLF on Windows. The Alpha 3 overlay has strict
# multiline guards, so normalize the rendered text to the overlay file's own
# newline convention before applying it. This changes formatting only.
$Alpha3PatchText = [System.IO.File]::ReadAllText($Alpha3EnginePatch, [System.Text.Encoding]::UTF8)
$UiText = $UiText.Replace("`r`n", "`n")
if ($Alpha3PatchText.Contains("`r`n")) {
    $UiText = $UiText.Replace("`n", "`r`n")
}

$UiText = & $Alpha3EnginePatchRunner -UiText $UiText
$UiText = & $QuietChatPatch -UiText $UiText
[System.IO.File]::WriteAllText($TempUi, $UiText, $Utf8Bom)

Write-Host "Starting Kadence Control Surface / Alpha 3 LOCAL-LUNA overlay..."
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
