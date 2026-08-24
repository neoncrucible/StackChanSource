param(
    [Parameter(Mandatory = $true)][string]$UiText
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

# Guarded runner for the Alpha 3 engine/chat overlay. The first Alpha 3 patch
# correctly prohibited AUTO routing, but its post-patch validator searched for
# the bare word AUTO. That also matched the deliberate operator log text
# "no AUTO", producing a false failure before the rendered UI could be tested.
#
# Keep the overlay itself intact and narrow only that validator at load time.
# The replacement is exact, single-use and fail-closed: if the source no longer
# matches the known checkpoint, this runner refuses to execute it.

$PatchPath = Join-Path $PSScriptRoot "KadenceControlPatchAlpha3Engine.ps1"
if (-not (Test-Path $PatchPath)) {
    throw "Alpha 3 engine patch not found: $PatchPath"
}

$Utf8 = [System.Text.Encoding]::UTF8
$PatchSource = [System.IO.File]::ReadAllText($PatchPath, $Utf8)

$OldValidator = @'
if ($Working.Contains('AUTO')) {
    throw "Alpha 3 Control Surface verification found forbidden AUTO routing text."
}
'@

$NewValidator = @'
foreach ($ForbiddenAutoMarker in @(
    '$autoEngineButton',
    '$autoButton',
    'Set-SelectedEngine -Engine "AUTO"',
    '$script:SelectedEngine = "AUTO"',
    '$autoEngineButton.Text = "AUTO"'
)) {
    if ($Working.Contains($ForbiddenAutoMarker)) {
        throw "Alpha 3 Control Surface verification found forbidden AUTO routing control: $ForbiddenAutoMarker"
    }
}
'@

$MatchCount = ([regex]::Matches($PatchSource, [regex]::Escape($OldValidator.TrimEnd()))).Count
if ($MatchCount -ne 1) {
    throw "Alpha 3 engine validator guard expected exactly one known AUTO validator; found $MatchCount."
}

$PatchedSource = $PatchSource.Replace($OldValidator.TrimEnd(), $NewValidator.TrimEnd())
if ($PatchedSource -eq $PatchSource) {
    throw "Alpha 3 engine validator guard made no change; refusing to continue."
}

$Tokens = $null
$ParseErrors = $null
$ScriptBlock = [System.Management.Automation.Language.Parser]::ParseInput(
    $PatchedSource,
    [ref]$Tokens,
    [ref]$ParseErrors
)
if (@($ParseErrors).Count -gt 0) {
    $Details = @($ParseErrors | ForEach-Object { "line $($_.Extent.StartLineNumber): $($_.Message)" }) -join "`r`n"
    throw "Alpha 3 engine validator guard produced invalid PowerShell:`r`n$Details"
}

$Executable = [scriptblock]::Create($PatchedSource)
return & $Executable -UiText $UiText
