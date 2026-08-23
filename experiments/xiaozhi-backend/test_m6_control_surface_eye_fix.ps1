$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = $PSScriptRoot
$UiScript = Join-Path $Root "control_surface/KadenceControlV3.ps1"
$PatchV4 = Join-Path $Root "control_surface/KadenceControlPatchV4.ps1"
$PatchV41 = Join-Path $Root "control_surface/KadenceControlPatchV41.ps1"
$PatchV43 = Join-Path $Root "control_surface/KadenceControlPatchV43.ps1"
$EyeFix = Join-Path $Root "control_surface/KadenceControlPatchEyeFix.ps1"
$Launcher = Join-Path $Root "start_control_surface.ps1"
$Alpha2Launcher = Join-Path $Root "start_alpha2_windows.ps1"
$Rollback = Join-Path $Root "remove_m7_behavior_windows.ps1"

foreach ($Path in @($UiScript,$PatchV4,$PatchV41,$PatchV43,$EyeFix,$Launcher,$Alpha2Launcher,$Rollback)) {
    if (-not (Test-Path $Path)) { throw "Missing M6 rollback test dependency: $Path" }
}

$UiText = [System.IO.File]::ReadAllText($UiScript,[System.Text.Encoding]::UTF8)
$UiText = & $PatchV4 -UiText $UiText
$UiText = & $PatchV41 -UiText $UiText
$UiText = & $PatchV43 -UiText $UiText
$UiText = & $EyeFix -UiText $UiText

foreach ($Marker in @(
    '$g.FillEllipse($glowBrush,76,31,128,128)',
    '$path.AddBezier(19,95,79,30,201,30,261,95)',
    'Canonical identity / GPT-5.6 Luna'
)) {
    if (-not $UiText.Contains($Marker)) { throw "FAIL missing M6+EYE marker: $Marker" }
}

foreach ($Forbidden in @(
    'SESSION BEHAVIOUR',
    'APPLY CUSTOM',
    '$BehaviorPort = 8766',
    'CUSTOM ACTIVE'
)) {
    if ($UiText.Contains($Forbidden)) { throw "FAIL M7 UI marker remains active: $Forbidden" }
}
Write-Host 'PASS  M6 Control Surface restored with eye fix and no M7 controls'

$LauncherText = [System.IO.File]::ReadAllText($Alpha2Launcher,[System.Text.Encoding]::UTF8)
if ($LauncherText.Contains('apply_m7_behavior_windows.ps1')) { throw 'FAIL active Alpha 2 launcher still applies M7' }
if (-not $LauncherText.Contains('remove_m7_behavior_windows.ps1')) { throw 'FAIL active Alpha 2 launcher does not clean prior M7 runtime state' }
if (-not $LauncherText.Contains('apply_kadence_tools_windows.ps1')) { throw 'FAIL active Alpha 2 launcher is not back on proven M6 tool applier' }
Write-Host 'PASS  active Alpha 2 launcher is M6-only and cleans prior M7 state'

foreach ($ScriptPath in @($Launcher,$Alpha2Launcher,$Rollback)) {
    $text = [System.IO.File]::ReadAllText($ScriptPath,[System.Text.Encoding]::UTF8)
    $tokens = $null
    $errors = $null
    [void][System.Management.Automation.Language.Parser]::ParseInput($text,[ref]$tokens,[ref]$errors)
    if ($errors.Count -gt 0) {
        $detail = ($errors | ForEach-Object { $_.Message }) -join '; '
        throw "FAIL PowerShell parse $ScriptPath: $detail"
    }
}
Write-Host 'PASS  M6 rollback scripts parse cleanly'
