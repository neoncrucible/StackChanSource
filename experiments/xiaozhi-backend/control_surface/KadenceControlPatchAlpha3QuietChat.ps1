param(
    [Parameter(Mandatory = $true)][string]$UiText
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

# Alpha 3 cosmetic/interaction overlay: use the WinForms form AcceptButton for
# Enter-to-send rather than a TextBox KeyDown handler. On Windows, the latter can
# emit the standard error/beep tone even though the message is successfully sent.
# This patch changes only Enter-key routing; mouse-click SEND behaviour is kept.

$OldBlock = @'
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

$NewBlock = @'
    $sendButton.add_Click($script:ChatSendAction)
    $chatForm.AcceptButton = $sendButton
'@

$Count = ([regex]::Matches($UiText, [regex]::Escape($OldBlock.TrimEnd()))).Count
if ($Count -ne 1) {
    throw "Alpha 3 quiet-chat patch expected exactly one Enter-key handler block; found $Count."
}

$Result = $UiText.Replace($OldBlock.TrimEnd(), $NewBlock.TrimEnd())

if (-not $Result.Contains('$chatForm.AcceptButton = $sendButton')) {
    throw "Alpha 3 quiet-chat patch did not install the WinForms AcceptButton."
}
if ($Result.Contains('$chatInput.add_KeyDown($script:ChatKeyDownAction)')) {
    throw "Alpha 3 quiet-chat patch left the old TextBox KeyDown handler active."
}

return $Result
