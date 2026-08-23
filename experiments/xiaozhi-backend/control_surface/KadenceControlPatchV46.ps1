param(
    [Parameter(Mandatory = $true)][string]$UiText
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

# V4.6 makes M7 state unambiguous to the operator. It changes UI signalling only;
# backend behaviour authority remains owned by the loopback M7 control plane.

$DefaultOriginal = @'
function Set-BehaviorUiDefault {
    $behaviorStatus.Text = "DEFAULT"
    $behaviorStatus.ForeColor = $ColorCyan
    $defaultBehaviorButton.FlatAppearance.BorderColor = $ColorCyan
    $applyCustomButton.FlatAppearance.BorderColor = $ColorCyan
}
'@
$DefaultPatched = @'
function Set-BehaviorUiDefault {
    $behaviorStatus.Text = "DEFAULT"
    $behaviorStatus.ForeColor = $ColorCyan
    $customBehaviorLabel.ForeColor = $ColorMuted
    $defaultBehaviorButton.FlatAppearance.BorderColor = $ColorCyan
    $applyCustomButton.FlatAppearance.BorderColor = $ColorCyan
}

function Set-BehaviorUiCustom {
    $behaviorStatus.Text = "CUSTOM ACTIVE"
    $behaviorStatus.ForeColor = $ColorAmber
    $customBehaviorLabel.ForeColor = $ColorAmber
    $defaultBehaviorButton.FlatAppearance.BorderColor = $ColorBorder
    $applyCustomButton.FlatAppearance.BorderColor = $ColorAmber
}
'@
if (-not $UiText.Contains($DefaultOriginal.TrimEnd())) {
    throw "Kadence Control V4.6 behaviour-state helper guard failed."
}
$UiText = $UiText.Replace($DefaultOriginal.TrimEnd(), $DefaultPatched.TrimEnd())

# Both the backend log observer and the successful APPLY CUSTOM click path used
# the same two-line status mutation. Route both through one visual-state helper.
$CustomStatusOriginal = @'
        $behaviorStatus.Text = "CUSTOM ACTIVE"
        $behaviorStatus.ForeColor = $ColorAmber
'@
if (([regex]::Matches($UiText, [regex]::Escape($CustomStatusOriginal.TrimEnd()))).Count -lt 2) {
    throw "Kadence Control V4.6 expected both CUSTOM status sites."
}
$UiText = $UiText.Replace($CustomStatusOriginal.TrimEnd(), '        Set-BehaviorUiCustom')

# A clickable but not-yet-ready button must explain itself instead of silently
# doing nothing. The editor remains usable before server startup as designed.
$UiText = $UiText.Replace(
    '$defaultBehaviorButton.add_Click({' + [Environment]::NewLine + '    if (-not $script:BehaviorReady) { return }',
    '$defaultBehaviorButton.add_Click({' + [Environment]::NewLine + '    if (-not $script:BehaviorReady) {' + [Environment]::NewLine + '        Append-Log "[KADENCE UI] M7 DEFAULT not applied: backend behaviour control is not ready."' + [Environment]::NewLine + '        return' + [Environment]::NewLine + '    }'
)
$UiText = $UiText.Replace(
    '$applyCustomButton.add_Click({' + [Environment]::NewLine + '    if (-not $script:BehaviorReady) { return }',
    '$applyCustomButton.add_Click({' + [Environment]::NewLine + '    if (-not $script:BehaviorReady) {' + [Environment]::NewLine + '        Append-Log "[KADENCE UI] M7 CUSTOM not applied: backend behaviour control is not ready."' + [Environment]::NewLine + '        return' + [Environment]::NewLine + '    }'
)

$UiText = $UiText.Replace(
    '[KADENCE UI] Control Surface V4.5 ready.',
    '[KADENCE UI] Control Surface V4.6 ready.'
)

foreach ($RequiredMarker in @(
    'function Set-BehaviorUiCustom {',
    '$customBehaviorLabel.ForeColor = $ColorAmber',
    '$applyCustomButton.FlatAppearance.BorderColor = $ColorAmber',
    '$customBehaviorLabel.ForeColor = $ColorMuted',
    'M7 CUSTOM not applied: backend behaviour control is not ready.',
    '[KADENCE UI] Control Surface V4.6 ready.'
)) {
    if (-not $UiText.Contains($RequiredMarker)) {
        throw "Kadence Control V4.6 post-patch verification failed: $RequiredMarker"
    }
}

return $UiText
