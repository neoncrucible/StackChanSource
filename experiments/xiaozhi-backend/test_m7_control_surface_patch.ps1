$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = $PSScriptRoot
$UiScript = Join-Path $Root "control_surface/KadenceControlV3.ps1"
$PatchV4 = Join-Path $Root "control_surface/KadenceControlPatchV4.ps1"
$PatchV41 = Join-Path $Root "control_surface/KadenceControlPatchV41.ps1"
$PatchV43 = Join-Path $Root "control_surface/KadenceControlPatchV43.ps1"
$PatchV44 = Join-Path $Root "control_surface/KadenceControlPatchV44.ps1"

foreach ($Path in @($UiScript,$PatchV4,$PatchV41,$PatchV43,$PatchV44)) {
    if (-not (Test-Path $Path)) {
        throw "Missing M7 Control Surface test dependency: $Path"
    }
}

$UiText = [System.IO.File]::ReadAllText($UiScript,[System.Text.Encoding]::UTF8)
$UiText = & $PatchV4 -UiText $UiText
$UiText = & $PatchV41 -UiText $UiText
$UiText = & $PatchV43 -UiText $UiText
$UiText = & $PatchV44 -UiText $UiText

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
Expect-Marker '$applyCustomButton.Text = "APPLY CUSTOM"' 'explicit Apply Custom action rendered'
Expect-Marker 'mode = "custom"; prompt = $custom' 'CUSTOM request sends explicit prompt'
Expect-Marker 'mode = "default"' 'DEFAULT request rendered'
Expect-Marker 'foreach ($port in @(8000,8003,8766))' 'preflight protects M7 loopback port'
Expect-Marker 'KADENCE BEHAVIOR: control ready' 'backend readiness handshake rendered'
Expect-Marker '$customBehaviorBox.Clear()' 'server lifecycle clears stale custom text'
Expect-Marker 'Canonical identity / GPT-5.6 Luna' 'current Luna-only identity survives M7 render'

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
