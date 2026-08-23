$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = $PSScriptRoot
$UiScript = Join-Path $Root "control_surface/KadenceControlV3.ps1"
$PatchV4 = Join-Path $Root "control_surface/KadenceControlPatchV4.ps1"
$PatchV41 = Join-Path $Root "control_surface/KadenceControlPatchV41.ps1"
$PatchV43 = Join-Path $Root "control_surface/KadenceControlPatchV43.ps1"
$PatchV44 = Join-Path $Root "control_surface/KadenceControlPatchV44.ps1"
$PatchV45 = Join-Path $Root "control_surface/KadenceControlPatchV45.ps1"
$ApplyM7 = Join-Path $Root "apply_m7_behavior_windows.ps1"

foreach ($Path in @($UiScript,$PatchV4,$PatchV41,$PatchV43,$PatchV44,$PatchV45,$ApplyM7)) {
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
Expect-Marker 'mode = "custom"; prompt = $custom' 'CUSTOM request sends explicit prompt'
Expect-Marker 'mode = "default"' 'DEFAULT request rendered'
Expect-Marker 'foreach ($port in @(8000,8003,8766))' 'preflight protects M7 loopback port'
Expect-Marker 'KADENCE BEHAVIOR: control ready' 'backend readiness handshake rendered'
Expect-Marker '$customBehaviorBox.Clear()' 'server lifecycle clears stale custom text'
Expect-Marker 'Canonical identity / GPT-5.6 Luna' 'current Luna-only identity survives M7 render'
Expect-Marker '$g.FillEllipse($glowBrush,76,31,128,128)' 'EYE glow scaled and centred'
Expect-Marker '$path.AddBezier(19,95,79,30,201,30,261,95)' 'EYE outline fits 280px panel'
Expect-Marker '[KADENCE UI] Control Surface V4.5 ready.' 'V4.5 render identified'

# Runtime applier regressions. Physical M7 testing exposed a missing newline that
# fused the behaviour import to the next Python import. Make newline ownership and
# repair of the already-broken local state explicit and testable.
$ApplyText = [System.IO.File]::ReadAllText($ApplyM7,[System.Text.Encoding]::UTF8)
if (-not $ApplyText.Contains('expected exactly one gc_manager.stop() site')) {
    throw 'FAIL  M7 shutdown patch is not using the unique executable shutdown anchor'
}
if (-not $ApplyText.Contains("'(?m)^        await gc_manager\.stop\(\)\s*$'")) {
    throw 'FAIL  M7 shutdown patch regex anchor is missing'
}
Write-Host 'PASS  M7 shutdown patch uses formatting-tolerant executable anchor'

$ExpectedImportAssignment = '$ConnImportPatched = "from core.kadence_tool_runtime import build_kadence_tool_handler`nfrom core.kadence_behavior import render_kadence_behavior_prompt`n"'
if (-not $ApplyText.Contains($ExpectedImportAssignment)) {
    throw 'FAIL  M7 connection import insertion does not explicitly own its trailing newline'
}
Write-Host 'PASS  M7 connection import insertion owns trailing newline'

if (-not $ApplyText.Contains('$LegacyFusedImport = "from core.kadence_behavior import render_kadence_behavior_promptfrom plugins_func.loadplugins import auto_import_modules"')) {
    throw 'FAIL  M7 applier does not recognise the physically observed fused-import runtime state'
}
if (-not $ApplyText.Contains('Repaired Kadence M7 legacy fused behaviour import.')) {
    throw 'FAIL  M7 applier does not report fused-import repair'
}
Write-Host 'PASS  M7 applier repairs physically observed fused import'

if (-not $ApplyText.Contains('$LegacyFusedRoot = "current_sentence_id = str(uuid.uuid4().hex)            self.sentence_id = current_sentence_id"')) {
    throw 'FAIL  M7 applier does not recognise possible fused root-turn runtime state'
}
if (-not $ApplyText.Contains('uuid.uuid4().hex)            self.sentence_id')) {
    throw 'FAIL  M7 applier does not guard residual fused root-turn state'
}
Write-Host 'PASS  M7 applier repairs/guards root-turn newline ownership'

# Syntax-parse the fully rendered script without launching WinForms. This catches
# quote/bracket errors in the patch chain while remaining safe on CI hosts.
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

Write-Host 'M7 Control Surface patch test: PASS'
