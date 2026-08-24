param()

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = $PSScriptRoot
$UiScript = Join-Path $Root "control_surface\KadenceControlV3.ps1"
$PatchV4 = Join-Path $Root "control_surface\KadenceControlPatchV4.ps1"
$PatchV41 = Join-Path $Root "control_surface\KadenceControlPatchV41.ps1"
$PatchV43 = Join-Path $Root "control_surface\KadenceControlPatchV43.ps1"
$EyeFix = Join-Path $Root "control_surface\KadenceControlPatchEyeFix.ps1"
$Alpha3Patch = Join-Path $Root "control_surface\KadenceControlPatchAlpha3Engine.ps1"
$Alpha3PatchRunner = Join-Path $Root "control_surface\InvokeKadenceControlPatchAlpha3Engine.ps1"
$Launcher = Join-Path $Root "start_control_surface.ps1"
$ChatBridge = Join-Path $Root "invoke_control_chat_windows.ps1"
$LocalStart = Join-Path $Root "start_local_windows.ps1"
$LocalStop = Join-Path $Root "stop_local_windows.ps1"
$LunaStart = Join-Path $Root "start_alpha2_windows.ps1"

foreach ($Path in @($UiScript,$PatchV4,$PatchV41,$PatchV43,$EyeFix,$Alpha3Patch,$Alpha3PatchRunner,$Launcher,$ChatBridge,$LocalStart,$LocalStop,$LunaStart)) {
    if (-not (Test-Path $Path)) {
        throw "FAIL missing Alpha 3 Control Surface dependency: $Path"
    }
}

Write-Host "=== Alpha 3 Control Surface static gate ==="

$LauncherText = [System.IO.File]::ReadAllText($Launcher,[System.Text.Encoding]::UTF8)
foreach ($RequiredLauncherMarker in @(
    'KadenceControlPatchV4.ps1',
    'KadenceControlPatchV41.ps1',
    'KadenceControlPatchV43.ps1',
    'KadenceControlPatchEyeFix.ps1',
    'KadenceControlPatchAlpha3Engine.ps1',
    'InvokeKadenceControlPatchAlpha3Engine.ps1'
)) {
    if (-not $LauncherText.Contains($RequiredLauncherMarker)) {
        throw "FAIL launcher is missing patch-chain marker: $RequiredLauncherMarker"
    }
}
foreach ($ForbiddenLauncherMarker in @(
    '& $PatchScriptV44',
    '& $PatchScriptV45',
    '& $PatchScriptV46',
    'apply_m7_behavior_windows.ps1'
)) {
    if ($LauncherText.Contains($ForbiddenLauncherMarker)) {
        throw "FAIL retired M7 path returned to active launcher: $ForbiddenLauncherMarker"
    }
}

$Rendered = [System.IO.File]::ReadAllText($UiScript,[System.Text.Encoding]::UTF8)
$Rendered = & $PatchV4 -UiText $Rendered
$Rendered = & $PatchV41 -UiText $Rendered
$Rendered = & $PatchV43 -UiText $Rendered
$Rendered = & $EyeFix -UiText $Rendered

# Match the launcher: strict multiline Alpha 3 guards must see the same newline
# convention as the Alpha 3 overlay file itself. This avoids false failures when
# older accepted files remain LF but newly pulled files are CRLF on Windows.
$Alpha3PatchText = [System.IO.File]::ReadAllText($Alpha3Patch,[System.Text.Encoding]::UTF8)
$Rendered = $Rendered.Replace("`r`n", "`n")
if ($Alpha3PatchText.Contains("`r`n")) {
    $Rendered = $Rendered.Replace("`n", "`r`n")
}

$Rendered = & $Alpha3PatchRunner -UiText $Rendered

foreach ($RequiredUiMarker in @(
    '$milestoneBadge.Text = "ALPHA 3"',
    '$localEngineButton.Text = "LOCAL"',
    '$lunaEngineButton.Text = "LUNA"',
    '$chatButton.Text = "CHAT"',
    '$LocalStartScript = Join-Path $BackendRoot "start_local_windows.ps1"',
    '$LocalStopScript = Join-Path $BackendRoot "stop_local_windows.ps1"',
    '$StartScript = Join-Path $BackendRoot "start_alpha2_windows.ps1"',
    '$ControlChatScript = Join-Path $BackendRoot "invoke_control_chat_windows.ps1"',
    'Starting LOCAL / qwen3.5:4b. No LUNA fallback is configured.',
    'Starting LUNA / frozen Alpha 2 backend. No LOCAL fallback is configured.',
    'Control Surface text context is separate from the robot voice session.',
    '$g.FillEllipse($glowBrush,76,31,128,128)'
)) {
    if (-not $Rendered.Contains($RequiredUiMarker)) {
        throw "FAIL rendered Alpha 3 UI is missing marker: $RequiredUiMarker"
    }
}

foreach ($ForbiddenUiMarker in @(
    'DEFAULT / CUSTOM',
    'CUSTOM BEHAVIOUR',
    '$autoEngineButton',
    'Set-SelectedEngine -Engine "AUTO"',
    '$script:SelectedEngine = "AUTO"'
)) {
    if ($Rendered.Contains($ForbiddenUiMarker)) {
        throw "FAIL forbidden retired/automatic UI marker present: $ForbiddenUiMarker"
    }
}

$Tokens = $null
$ParseErrors = $null
$null = [System.Management.Automation.Language.Parser]::ParseInput($Rendered,[ref]$Tokens,[ref]$ParseErrors)
if (@($ParseErrors).Count -gt 0) {
    $Details = @($ParseErrors | ForEach-Object { "line $($_.Extent.StartLineNumber): $($_.Message)" }) -join "`r`n"
    throw "FAIL rendered Alpha 3 Control Surface has PowerShell parse errors:`r`n$Details"
}

$ChatText = [System.IO.File]::ReadAllText($ChatBridge,[System.Text.Encoding]::UTF8)
foreach ($RequiredChatMarker in @(
    '[ValidateSet("LOCAL","LUNA")]',
    'qwen3.5:4b',
    'gpt-5.6-luna',
    'reasoning_effort = "none"',
    'Get-KadenceCanonicalPersona',
    'LUNA backend is not listening on TCP 8000',
    'LOCAL ownership verification failed'
)) {
    if (-not $ChatText.Contains($RequiredChatMarker)) {
        throw "FAIL chat bridge missing fail-closed marker: $RequiredChatMarker"
    }
}

$ChatTokens = $null
$ChatParseErrors = $null
$null = [System.Management.Automation.Language.Parser]::ParseInput($ChatText,[ref]$ChatTokens,[ref]$ChatParseErrors)
if (@($ChatParseErrors).Count -gt 0) {
    $Details = @($ChatParseErrors | ForEach-Object { "line $($_.Extent.StartLineNumber): $($_.Message)" }) -join "`r`n"
    throw "FAIL chat bridge has PowerShell parse errors:`r`n$Details"
}

$RepoRoot = (Resolve-Path (Join-Path $Root "..\..")).Path
$FirmwareDelta = @(git -C $RepoRoot diff --name-only c74d8949f33c6dea1d7df2bea248cad9e82d5dd1..HEAD -- firmware)
if ($LASTEXITCODE -ne 0) {
    throw "FAIL git firmware provenance check could not run."
}
if ($FirmwareDelta.Count -ne 0) {
    throw "FAIL Alpha 3 branch contains committed firmware changes:`r`n$($FirmwareDelta -join "`r`n")"
}

Write-Host "PASS patch chain: accepted M6 + EYE -> Alpha 3 overlay"
Write-Host "PASS explicit engine selection: LOCAL / LUNA only"
Write-Host "PASS no automatic engine selector and no retired M7 behaviour controls"
Write-Host "PASS LOCAL path: start_local_windows.ps1 / stop_local_windows.ps1"
Write-Host "PASS LUNA path: frozen start_alpha2_windows.ps1"
Write-Host "PASS Control Surface chat bridge: selected engine only / no fallback"
Write-Host "PASS rendered UI and chat bridge parse cleanly"
Write-Host "PASS no committed firmware delta from frozen Alpha 2 closure"
Write-Host ""
Write-Host "STATIC GATE COMPLETE - physical UI behaviour is not yet validated."
