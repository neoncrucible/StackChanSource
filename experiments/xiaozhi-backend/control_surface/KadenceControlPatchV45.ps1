param(
    [Parameter(Mandatory = $true)][string]$UiText
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

# V4.5 is a visual/usability repair over the already-rendered V4.4 M7 surface.
# It does not change the M7 authority model or backend transport.

# ---------------------------------------------------------------------------
# M7 editor/buttons: keep the free-text editor usable even when the backend is
# offline, and keep both actions visually consistent with START SERVER. Runtime
# readiness is still enforced by the existing click handlers.
# ---------------------------------------------------------------------------
$UiText = $UiText.Replace(
    '$defaultBehaviorButton.BackColor = $ColorPanel',
    '$defaultBehaviorButton.BackColor = $ColorPanelAlt'
)
$UiText = $UiText.Replace(
    '$defaultBehaviorButton.ForeColor = $ColorOffline',
    '$defaultBehaviorButton.ForeColor = $ColorCyan'
)
$UiText = $UiText.Replace(
    '$defaultBehaviorButton.Enabled = $false',
    '$defaultBehaviorButton.Enabled = $true'
)
$UiText = $UiText.Replace(
    '$applyCustomButton.BackColor = $ColorPanel',
    '$applyCustomButton.BackColor = $ColorPanelAlt'
)
$UiText = $UiText.Replace(
    '$applyCustomButton.ForeColor = $ColorOffline',
    '$applyCustomButton.ForeColor = $ColorCyan'
)
$UiText = $UiText.Replace(
    '$applyCustomButton.Enabled = $false',
    '$applyCustomButton.Enabled = $true'
)
$UiText = $UiText.Replace(
    '$customBehaviorBox.Enabled = $false',
    '$customBehaviorBox.Enabled = $true'
)

$ReadyFunctionOriginal = @'
function Set-BehaviorControlsReady {
    param([bool]$Ready)
    $script:BehaviorReady = $Ready
    $defaultBehaviorButton.Enabled = $Ready
    $applyCustomButton.Enabled = $Ready
    $customBehaviorBox.Enabled = $Ready
    if ($Ready) {
        $defaultBehaviorButton.ForeColor = $ColorCyan
        $applyCustomButton.ForeColor = $ColorCyan
    } else {
        $defaultBehaviorButton.ForeColor = $ColorOffline
        $applyCustomButton.ForeColor = $ColorOffline
    }
}
'@
$ReadyFunctionPatched = @'
function Set-BehaviorControlsReady {
    param([bool]$Ready)
    $script:BehaviorReady = $Ready

    # The editor is deliberately usable while offline so an operator can prepare
    # a CUSTOM prompt. Buttons remain readable/clickable; their existing handlers
    # still refuse to send anything until the loopback control plane is ready.
    $defaultBehaviorButton.Enabled = $true
    $applyCustomButton.Enabled = $true
    $customBehaviorBox.Enabled = $true
    $defaultBehaviorButton.ForeColor = $ColorCyan
    $applyCustomButton.ForeColor = $ColorCyan
}
'@
if (-not $UiText.Contains($ReadyFunctionOriginal.TrimEnd())) {
    throw "Kadence Control V4.5 behaviour-ready function guard failed."
}
$UiText = $UiText.Replace(
    $ReadyFunctionOriginal.TrimEnd(),
    $ReadyFunctionPatched.TrimEnd()
)

# ---------------------------------------------------------------------------
# EYE geometry: V4 narrowed the left rail to a 280px eye panel but retained
# geometry extending to x=290, which clipped the right edge. Scale the graphic
# to 90% and recenter it at (140,95) inside the 280x190 panel.
# ---------------------------------------------------------------------------
$EyeReplacements = @(
    @('$g.FillEllipse($glowBrush,85,8,142,142)', '$g.FillEllipse($glowBrush,76,31,128,128)'),
    @('$path.AddBezier(22,79,88,7,224,7,290,79)', '$path.AddBezier(19,95,79,30,201,30,261,95)'),
    @('$path.AddBezier(290,79,224,151,88,151,22,79)', '$path.AddBezier(261,95,201,160,79,160,19,95)'),
    @('$g.FillEllipse($irisBrush,109,32,94,94)', '$g.FillEllipse($irisBrush,98,53,85,85)'),
    @('$g.DrawEllipse($ringPen,109,32,94,94)', '$g.DrawEllipse($ringPen,98,53,85,85)'),
    @('$g.DrawEllipse($ringPen,126,49,60,60)', '$g.DrawEllipse($ringPen,113,68,54,54)'),
    @('$g.FillEllipse($pupilBrush,146,69,20,20)', '$g.FillEllipse($pupilBrush,131,86,18,18)'),
    @('$g.DrawLine($ringPen,156,22,156,37)', '$g.DrawLine($ringPen,140,44,140,57)'),
    @('$g.DrawLine($ringPen,156,121,156,136)', '$g.DrawLine($ringPen,140,133,140,146)'),
    @('$g.DrawLine($ringPen,99,79,114,79)', '$g.DrawLine($ringPen,89,95,102,95)'),
    @('$g.DrawLine($ringPen,198,79,213,79)', '$g.DrawLine($ringPen,178,95,191,95)')
)
foreach ($Pair in $EyeReplacements) {
    if (-not $UiText.Contains($Pair[0])) {
        throw "Kadence Control V4.5 eye-geometry guard failed: $($Pair[0])"
    }
    $UiText = $UiText.Replace($Pair[0], $Pair[1])
}

# Version labels for the rendered UI.
$UiText = $UiText.Replace(
    '[KADENCE UI] Control Surface V4.4 ready.',
    '[KADENCE UI] Control Surface V4.5 ready.'
)

foreach ($RequiredMarker in @(
    '$customBehaviorBox.Enabled = $true',
    '$defaultBehaviorButton.BackColor = $ColorPanelAlt',
    '$applyCustomButton.BackColor = $ColorPanelAlt',
    '$g.FillEllipse($glowBrush,76,31,128,128)',
    '$path.AddBezier(19,95,79,30,201,30,261,95)'
)) {
    if (-not $UiText.Contains($RequiredMarker)) {
        throw "Kadence Control V4.5 post-patch verification failed: $RequiredMarker"
    }
}

return $UiText
