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
# overlay source intact and replace only the known list-conversion sites with
# direct enumeration / ToArray().
#
# A second Windows PowerShell 5.1 issue appears when GetNewClosure() is used for
# the CHAT send handler: $script: state resolves inside the closure's dynamic
# module rather than the Control Surface script, and the Enter handler later
# cannot retrieve the local $SendAction variable. Replace that whole known event
# block with script-scoped control references and script-scoped handlers.
# Every replacement is exact and fail-closed.

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

$OldSendBlock = @'
    $SendAction = {
        $Text = $chatInput.Text.Trim()
        if ([string]::IsNullOrWhiteSpace($Text)) { return }

        $EngineRunning = if ($script:SelectedEngine -eq "LOCAL") {
            $script:LocalRunning
        } else {
            (($null -ne $script:BackendProcess) -and (-not $script:BackendProcess.HasExited))
        }
        if (-not $EngineRunning) {
            $chatStatus.Text = ("{0} is not running." -f $script:SelectedEngine)
            $chatStatus.ForeColor = $ColorRed
            return
        }

        $chatInput.Clear()
        $transcript.AppendText(("YOU> {0}`r`n`r`n" -f $Text))
        $transcript.SelectionStart = $transcript.TextLength
        $transcript.ScrollToCaret()
        $script:ChatMessages.Add([pscustomobject]@{ role = "user"; content = $Text })

        while ($script:ChatMessages.Count -gt 16) {
            $script:ChatMessages.RemoveAt(0)
        }

        $sendButton.Enabled = $false
        $chatInput.Enabled = $false
        $chatStatus.Text = ("{0} is thinking..." -f $script:SelectedEngine)
        $chatStatus.ForeColor = $ColorAmber
        [System.Windows.Forms.Application]::DoEvents()

        try {
            $History = $script:ChatMessages.ToArray()
            $Result = & $ControlChatScript -Engine $script:SelectedEngine -Messages $History
            $Reply = [string]$Result.Text
            $script:ChatMessages.Add([pscustomobject]@{ role = "assistant"; content = $Reply })
            while ($script:ChatMessages.Count -gt 16) {
                $script:ChatMessages.RemoveAt(0)
            }

            $transcript.AppendText(("KADENCE> {0}`r`n`r`n" -f $Reply))
            $transcript.SelectionStart = $transcript.TextLength
            $transcript.ScrollToCaret()
            $chatStatus.Text = ("{0} / {1} / {2:N0} ms" -f $Result.Engine,$Result.Model,[double]$Result.WallMilliseconds)
            $chatStatus.ForeColor = $ColorTeal
        }
        catch {
            $transcript.AppendText(("[ERROR] {0}`r`n`r`n" -f $_.Exception.Message))
            $transcript.SelectionStart = $transcript.TextLength
            $transcript.ScrollToCaret()
            $chatStatus.Text = "Chat request failed. No alternate engine was attempted."
            $chatStatus.ForeColor = $ColorRed
        }
        finally {
            $sendButton.Enabled = $true
            $chatInput.Enabled = $true
            $chatInput.Focus()
        }
    }.GetNewClosure()

    $sendButton.add_Click($SendAction)
    $chatInput.add_KeyDown({
        param($sender,$e)
        if ($e.KeyCode -eq [System.Windows.Forms.Keys]::Enter) {
            $e.SuppressKeyPress = $true
            & $SendAction
        }
    })
'@

$NewSendBlock = @'
    $script:ChatInputControl = $chatInput
    $script:ChatTranscriptControl = $transcript
    $script:ChatStatusControl = $chatStatus
    $script:ChatSendButtonControl = $sendButton
    $script:ChatControlScriptPath = $ControlChatScript

    $script:ChatSendAction = {
        $Text = $script:ChatInputControl.Text.Trim()
        if ([string]::IsNullOrWhiteSpace($Text)) { return }

        $EngineRunning = if ($script:SelectedEngine -eq "LOCAL") {
            $script:LocalRunning
        } else {
            (($null -ne $script:BackendProcess) -and (-not $script:BackendProcess.HasExited))
        }
        if (-not $EngineRunning) {
            $script:ChatStatusControl.Text = ("{0} is not running." -f $script:SelectedEngine)
            $script:ChatStatusControl.ForeColor = $ColorRed
            return
        }

        $script:ChatInputControl.Clear()
        $script:ChatTranscriptControl.AppendText(("YOU> {0}`r`n`r`n" -f $Text))
        $script:ChatTranscriptControl.SelectionStart = $script:ChatTranscriptControl.TextLength
        $script:ChatTranscriptControl.ScrollToCaret()
        $script:ChatMessages.Add([pscustomobject]@{ role = "user"; content = $Text })

        while ($script:ChatMessages.Count -gt 16) {
            $script:ChatMessages.RemoveAt(0)
        }

        $script:ChatSendButtonControl.Enabled = $false
        $script:ChatInputControl.Enabled = $false
        $script:ChatStatusControl.Text = ("{0} is thinking..." -f $script:SelectedEngine)
        $script:ChatStatusControl.ForeColor = $ColorAmber
        [System.Windows.Forms.Application]::DoEvents()

        try {
            $History = $script:ChatMessages.ToArray()
            $Result = & $script:ChatControlScriptPath -Engine $script:SelectedEngine -Messages $History
            $Reply = [string]$Result.Text
            $script:ChatMessages.Add([pscustomobject]@{ role = "assistant"; content = $Reply })
            while ($script:ChatMessages.Count -gt 16) {
                $script:ChatMessages.RemoveAt(0)
            }

            $script:ChatTranscriptControl.AppendText(("KADENCE> {0}`r`n`r`n" -f $Reply))
            $script:ChatTranscriptControl.SelectionStart = $script:ChatTranscriptControl.TextLength
            $script:ChatTranscriptControl.ScrollToCaret()
            $script:ChatStatusControl.Text = ("{0} / {1} / {2:N0} ms" -f $Result.Engine,$Result.Model,[double]$Result.WallMilliseconds)
            $script:ChatStatusControl.ForeColor = $ColorTeal
        }
        catch {
            $script:ChatTranscriptControl.AppendText(("[ERROR] {0}`r`n`r`n" -f $_.Exception.Message))
            $script:ChatTranscriptControl.SelectionStart = $script:ChatTranscriptControl.TextLength
            $script:ChatTranscriptControl.ScrollToCaret()
            $script:ChatStatusControl.Text = "Chat request failed. No alternate engine was attempted."
            $script:ChatStatusControl.ForeColor = $ColorRed
        }
        finally {
            $script:ChatSendButtonControl.Enabled = $true
            $script:ChatInputControl.Enabled = $true
            $script:ChatInputControl.Focus()
        }
    }

    $script:ChatKeyDownAction = {
        param($sender,$e)
        if ($e.KeyCode -eq [System.Windows.Forms.Keys]::Enter) {
            $e.SuppressKeyPress = $true
            & $script:ChatSendAction
        }
    }

    $sendButton.add_Click($script:ChatSendAction)
    $chatInput.add_KeyDown($script:ChatKeyDownAction)
'@

$SendBlockCount = ([regex]::Matches($PatchedSource, [regex]::Escape($OldSendBlock.TrimEnd()))).Count
if ($SendBlockCount -ne 1) {
    throw "Alpha 3 chat event-scope guard expected one known send-handler block; found $SendBlockCount."
}
$PatchedSource = $PatchedSource.Replace($OldSendBlock.TrimEnd(), $NewSendBlock.TrimEnd())

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
