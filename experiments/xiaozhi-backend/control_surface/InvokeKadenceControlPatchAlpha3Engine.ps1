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
# Windows PowerShell 5.1 also throws "Argument types do not match" when the
# WinForms CHAT handler forces Generic.List[object] through @(...). Keep the
# overlay source intact and replace only the two known list-conversion sites with
# direct enumeration / ToArray(). Every replacement is exact and fail-closed.

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

$OldHistoryEnumeration = '    foreach ($HistoryItem in @($script:ChatMessages)) {'
$NewHistoryEnumeration = '    foreach ($HistoryItem in $script:ChatMessages) {'
$HistoryEnumerationCount = ([regex]::Matches($PatchedSource, [regex]::Escape($OldHistoryEnumeration))).Count
if ($HistoryEnumerationCount -ne 1) {
    throw "Alpha 3 chat compatibility guard expected one history enumeration; found $HistoryEnumerationCount."
}
$PatchedSource = $PatchedSource.Replace($OldHistoryEnumeration, $NewHistoryEnumeration)

$OldHistoryCopy = '            $History = @($script:ChatMessages | ForEach-Object { $_ })'
$NewHistoryCopy = '            $History = $script:ChatMessages.ToArray()'
$HistoryCopyCount = ([regex]::Matches($PatchedSource, [regex]::Escape($OldHistoryCopy))).Count
if ($HistoryCopyCount -ne 1) {
    throw "Alpha 3 chat compatibility guard expected one history copy; found $HistoryCopyCount."
}
$PatchedSource = $PatchedSource.Replace($OldHistoryCopy, $NewHistoryCopy)

$Tokens = $null
$ParseErrors = $null
$ScriptBlock = [System.Management.Automation.Language.Parser]::ParseInput(
    $PatchedSource,
    [ref]$Tokens,
    [ref]$ParseErrors
)
if (@($ParseErrors).Count -gt 0) {
    $Details = @($ParseErrors | ForEach-Object { "line $($_.Extent.StartLineNumber): $($_.Message)" }) -join "`r`n"
    throw "Alpha 3 engine compatibility guard produced invalid PowerShell:`r`n$Details"
}

$Executable = [scriptblock]::Create($PatchedSource)
return & $Executable -UiText $UiText
