param(
    [Parameter(Mandatory = $true)][string]$UiText
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

# V4.1 header cleanup. Keep PROJECT KADENCE as the sole left-side product name,
# retain only the durable Alpha 2 phase badge, and remove milestone numbering
# because milestones are development bookkeeping rather than runtime state.
$UiText = $UiText.Replace('$subtitle.Text = "ALPHA 2  /  CONTROL SURFACE"', '$subtitle.Text = ""')
$UiText = $UiText.Replace('$milestoneBadge.Text = "ALPHA 2  //  MILESTONE 3"', '$milestoneBadge.Text = "ALPHA 2"')
$UiText = $UiText.Replace('$milestoneBadge.Size = New-Object System.Drawing.Size(178,28)', '$milestoneBadge.Size = New-Object System.Drawing.Size(92,28)')
$UiText = $UiText.Replace('$milestoneBadge.Location = New-Object System.Drawing.Point(1015,22)', '$milestoneBadge.Location = New-Object System.Drawing.Point(1101,22)')

return $UiText
