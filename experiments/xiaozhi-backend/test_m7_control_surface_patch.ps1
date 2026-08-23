$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = $PSScriptRoot
$UiScript = Join-Path $Root "control_surface/KadenceControlV3.ps1"
$PatchV4 = Join-Path $Root "control_surface/KadenceControlPatchV4.ps1"
$PatchV41 = Join-Path $Root "control_surface/KadenceControlPatchV41.ps1"
$PatchV43 = Join-Path $Root "control_surface/KadenceControlPatchV43.ps1"
$PatchV44 = Join-Path $Root "control_surface/KadenceControlPatchV44.ps1"
$PatchV45 = Join-Path $Root "control_surface/KadenceControlPatchV45.ps1"
$PatchV46 = Join-Path $Root "control_surface/KadenceControlPatchV46.ps1"
$ApplyM7 = Join-Path $Root "apply_m7_behavior_windows.ps1"

foreach ($Path in @($UiScript,$PatchV4,$PatchV41,$PatchV43,$PatchV44,$PatchV45,$PatchV46,$ApplyM7)) {
    if (-not (Test-Path $Path)) {
        throw "Missing M7 Control Surface test dependency: $Path"
    }
}

$UiText = [System.IO.File]::ReadAllText($UiScript,[System.Text.Encoding]::UTF8)
$UiText = & $PatchV4 -UiText $UiText
$UiText = & $PatchV41 -UiText $UiText
$UiText = & $PatchV43 -UiText $UiText
$UiText = & $PatchV44 -UiText $UiText
$UiText = & $PatchV45 -UiText $UiText
$UiText = & $PatchV46 -UiText $UiText

function Expect-Marker {
    param([Parameter(Mandatory=$true)][string]$Marker,[Parameter(Mandatory=$true)][string]$Label)
    if (-not $UiText.Contains($Marker)) {
        throw "FAIL  $Label / missing marker: $Marker"
    }
    Write-Host "PASS  $Label"
}

Expect-Marker '$BehaviorPort = 8766' 'M7 loopback control port rendered'
Expect-Marker '$BehaviorUri = "http://127.0.0.1:$BehaviorPort/v1/behavior"' 'M7 loopback URI rendered'
Expect-Marker '$behaviorTitle.Text = "SESSION BEHAVIOUR"' 'M7 behaviour card rendered'
Expect-Marker '$defaultBehaviorButton.Text = "DEFAULT"' 'DEFAULT action rendered'
Expect-Marker '$customBehaviorLabel.Text = "CUSTOM"' 'CUSTOM label rendered'
Expect-Marker '$customBehaviorBox.MaxLength = 1000' 'CUSTOM editor bounded to 1000 chars'
Expect-Marker '$customBehaviorBox.Enabled = $true' 'CUSTOM editor remains writable while offline'
Expect-Marker '$applyCustomButton.Text = "APPLY CUSTOM"' 'explicit Apply Custom action rendered'
Expect-Marker '$defaultBehaviorButton.BackColor = $ColorPanelAlt' 'DEFAULT button matches server-button surface'
Expect-Marker '$applyCustomButton.BackColor = $ColorPanelAlt' 'APPLY CUSTOM button matches server-button surface'
Expect-Marker '$defaultBehaviorButton.ForeColor = $ColorCyan' 'DEFAULT button remains readable'
Expect-Marker '$applyCustomButton.ForeColor = $ColorCyan' 'APPLY CUSTOM button remains readable'
Expect-Marker 'function Set-BehaviorUiCustom {' 'CUSTOM visual state helper rendered'
Expect-Marker '$customBehaviorLabel.ForeColor = $ColorAmber' 'CUSTOM word highlights when active'
Expect-Marker '$applyCustomButton.FlatAppearance.BorderColor = $ColorAmber' 'CUSTOM button highlights when active'
Expect-Marker '$customBehaviorLabel.ForeColor = $ColorMuted' 'DEFAULT restores muted CUSTOM label'
Expect-Marker 'M7 CUSTOM not applied: backend behaviour control is not ready.' 'premature CUSTOM action reports why it was refused'
Expect-Marker 'mode = "custom"; prompt = $custom' 'CUSTOM request sends explicit prompt'
Expect-Marker 'mode = "default"' 'DEFAULT request rendered'
Expect-Marker 'foreach ($port in @(8000,8003,8766))' 'preflight protects M7 loopback port'
Expect-Marker 'KADENCE BEHAVIOR: control ready' 'backend readiness handshake rendered'
Expect-Marker '$customBehaviorBox.Clear()' 'server lifecycle clears stale custom text'
Expect-Marker 'Canonical identity / GPT-5.6 Luna' 'current Luna-only identity survives M7 render'
Expect-Marker '$g.FillEllipse($glowBrush,76,31,128,128)' 'EYE glow scaled and centred'
Expect-Marker '$path.AddBezier(19,95,79,30,201,30,261,95)' 'EYE outline fits 280px panel'
Expect-Marker '[KADENCE UI] Control Surface V4.6 ready.' 'V4.6 render identified'

$ApplyText = [System.IO.File]::ReadAllText($ApplyM7,[System.Text.Encoding]::UTF8)
if (-not $ApplyText.Contains('expected exactly one gc_manager.stop() site')) {
    throw 'FAIL  M7 shutdown patch is not using the unique executable shutdown anchor'
}
if (-not $ApplyText.Contains("'(?m)^        await gc_manager\.stop\(\)\s*$'")) {
    throw 'FAIL  M7 shutdown patch regex anchor is missing'
}
Write-Host 'PASS  M7 shutdown patch uses formatting-tolerant executable anchor'

if (-not $ApplyText.Contains('get_kadence_behavior_snapshot')) {
    throw 'FAIL  M7 runtime patch does not read live behaviour state per turn'
}
if (-not $ApplyText.Contains('KADENCE BEHAVIOR: turn mode=')) {
    throw 'FAIL  M7 runtime patch does not log per-turn behaviour state'
}
Write-Host 'PASS  M7 runtime traces live mode at each top-level turn'

if (-not $ApplyText.Contains('$LegacyFusedImport = "from core.kadence_behavior import render_kadence_behavior_promptfrom plugins_func.loadplugins import auto_import_modules"')) {
    throw 'FAIL  M7 applier does not recognise the physically observed fused-import runtime state'
}
if (-not $ApplyText.Contains('Repaired Kadence M7 legacy fused behaviour import.')) {
    throw 'FAIL  M7 applier does not report fused-import repair'
}
Write-Host 'PASS  M7 applier retains legacy fused-import repair'

# Parse both generated UI and runtime applier. The latter matters because it
# writes Python source into the ignored local runtime during every server start.
$tokens = $null
$errors = $null
[void][System.Management.Automation.Language.Parser]::ParseInput(
    $UiText,
    [ref]$tokens,
    [ref]$errors
)
if ($errors.Count -gt 0) {
    $detail = ($errors | ForEach-Object { $_.Message }) -join '; '
    throw "FAIL  rendered Control Surface PowerShell syntax: $detail"
}
Write-Host 'PASS  rendered Control Surface PowerShell syntax'

$applyTokens = $null
$applyErrors = $null
[void][System.Management.Automation.Language.Parser]::ParseInput(
    $ApplyText,
    [ref]$applyTokens,
    [ref]$applyErrors
)
if ($applyErrors.Count -gt 0) {
    $detail = ($applyErrors | ForEach-Object { $_.Message }) -join '; '
    throw "FAIL  M7 runtime applier PowerShell syntax: $detail"
}
Write-Host 'PASS  M7 runtime applier PowerShell syntax'

Write-Host 'M7 Control Surface patch test: PASS'
