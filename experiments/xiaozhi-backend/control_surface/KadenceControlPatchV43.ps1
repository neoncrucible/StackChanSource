param(
    [Parameter(Mandatory = $true)][string]$UiText
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

# Post-M5 provider simplification. Alpha 2 is deliberately Luna-only from M6
# onward. LOCAL/LUNA selection belongs to the future beta/live control surface
# once a local inference engine actually exists.
$UiText = $UiText.Replace(
    'Canonical identity / Selected LLM',
    'Canonical identity / GPT-5.6 Luna'
)
$UiText = $UiText.Replace(
    '@{Name="LLM";Value="Selected pre-boot"},',
    '@{Name="LLM";Value="GPT-5.6 Luna"},'
)
$UiText = $UiText.Replace(
    '$modelHealth = New-PanelLabel "MODEL  WAITING"',
    '$modelHealth = New-PanelLabel "MODEL  GPT-5.6 LUNA"'
)

return $UiText
