param(
    [Parameter(Mandatory = $true)][string]$UiText
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

# Post-M6 cosmetic repair only.
# The V4 layout narrowed the left rail to a 280 px eye panel while the original
# drawing still extended beyond that width. Scale the EYE to 90% and recenter it
# at (140,95). No M7 controls, behaviour state or backend logic are introduced.
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
        throw "Kadence M6 EYE-fix guard failed: $($Pair[0])"
    }
    $UiText = $UiText.Replace($Pair[0], $Pair[1])
}

foreach ($RequiredMarker in @(
    '$g.FillEllipse($glowBrush,76,31,128,128)',
    '$path.AddBezier(19,95,79,30,201,30,261,95)',
    '$path.AddBezier(261,95,201,160,79,160,19,95)'
)) {
    if (-not $UiText.Contains($RequiredMarker)) {
        throw "Kadence M6 EYE-fix verification failed: $RequiredMarker"
    }
}

return $UiText
