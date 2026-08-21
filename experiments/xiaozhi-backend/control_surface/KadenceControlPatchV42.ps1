param(
    [Parameter(Mandatory = $true)][string]$UiText
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

# V4.2 is deliberately inert during normal operation. It activates only when
# m3_stage_c_windows.ps1 has created a local active Stage C session marker.
# In that mode it masks the LLM identity in the visible Control Surface while
# retaining the raw backend log in the local Stage C evidence folder.
$BackendRoot = Split-Path $PSScriptRoot -Parent
$ActiveSessionPath = Join-Path $BackendRoot ".runtime\benchmarks\m3-stage-c\active_session.json"

if (-not (Test-Path $ActiveSessionPath)) {
    return $UiText
}

try {
    $Session = [System.IO.File]::ReadAllText($ActiveSessionPath, [System.Text.Encoding]::UTF8) | ConvertFrom-Json
}
catch {
    throw "M3 Stage C blind session marker is unreadable: $ActiveSessionPath"
}

$Label = ([string]$Session.active_label).Trim().ToUpperInvariant()
if ($Label -notin @("A", "B")) {
    throw "M3 Stage C blind session has invalid active_label '$Label'."
}

$RunDir = [string]$Session.run_dir
if ([string]::IsNullOrWhiteSpace($RunDir) -or (-not (Test-Path $RunDir))) {
    throw "M3 Stage C run directory is missing: '$RunDir'."
}

$BlindModel = "MODEL  BLIND $Label"
$BlindMode = "Canonical identity / Blind profile $Label"
$BlindStack = "Blind profile $Label"

# Mask every model-facing label created by V3/V4. These replacements affect
# display strings only; provider configuration and server startup remain intact.
foreach ($Pair in @(
    @('"MODEL  WAITING"', ('"' + $BlindModel + '"')),
    @('"MODEL  GEMINI"', ('"' + $BlindModel + '"')),
    @('"MODEL  GPT-5.6 LUNA"', ('"' + $BlindModel + '"')),
    @('"Canonical identity / Selected LLM"', ('"' + $BlindMode + '"')),
    @('"Canonical identity / Gemini Flash-Lite"', ('"' + $BlindMode + '"')),
    @('"Canonical identity / GPT-5.6 Luna"', ('"' + $BlindMode + '"')),
    @('"Gemini 3.5 Flash-Lite"', ('"' + $BlindStack + '"')),
    @('"GPT-5.6 Luna"', ('"' + $BlindStack + '"'))
)) {
    $UiText = $UiText.Replace([string]$Pair[0], [string]$Pair[1])
}

# Visible live-log redaction. The raw backend log stays untouched on disk so the
# provider can be unmasked later for timing analysis. Redact only model/provider
# identity; ASR's OpenAI Realtime identity remains visible because it is a fixed
# Stage C variable rather than the LLM under test.
$ProcessNeedle = @'
function Process-ServerLine {
    param([string]$Line)
    Append-Log $Line
'@

$ProcessBlock = @'
function Process-ServerLine {
    param([string]$Line)
    $Line = $Line -replace 'Applying pre-boot LLM profile:\s*(?:gemini|luna)', 'Applying pre-boot LLM profile: BLIND __LABEL__'
    $Line = $Line -replace 'Kadence LLM profile:\s*openai-luna[^\r\n]*', 'Kadence LLM profile: BLIND __LABEL__'
    $Line = $Line -replace 'Kadence LLM profile:\s*gemini[^\r\n]*', 'Kadence LLM profile: BLIND __LABEL__'
    $Line = $Line -replace '\bOpenAILLM\b', 'BlindLLM'
    $Line = $Line -replace '\bGeminiLLM\b', 'BlindLLM'
    $Line = $Line -replace '\bgpt-5\.6-luna\b', 'blind-model'
    $Line = $Line -replace '\bgemini-3\.5-flash-lite\b', 'blind-model'
    $Line = $Line -replace '\bopenai-luna\b', 'blind-profile'
    $Line = $Line -replace '\bGemini\b', 'blind-profile'
    $Line = $Line -replace '\bLuna\b', 'blind-profile'
    Append-Log $Line
'@
$ProcessBlock = $ProcessBlock.Replace("__LABEL__", $Label)

if (-not $UiText.Contains($ProcessNeedle.TrimEnd())) {
    throw "M3 Stage C blind patch could not locate Process-ServerLine; refusing to launch an unmasked UI."
}
$UiText = $UiText.Replace($ProcessNeedle.TrimEnd(), $ProcessBlock.TrimEnd())

# Preserve each blind run's raw server output under a stable local evidence path
# instead of the ordinary random TEMP log. The visible UI consumes the same file
# through its existing proven tailing logic.
$RawLogPath = Join-Path $RunDir ("{0}-server.log" -f $Label)
$EscapedRawLogPath = $RawLogPath.Replace("'", "''")
$LogNeedle = '$script:BackendLogPath = Join-Path $env:TEMP ("kadence-alpha2-{0}.log" -f $token)'
$LogReplacement = '$script:BackendLogPath = ''' + $EscapedRawLogPath + ''''
if (-not $UiText.Contains($LogNeedle)) {
    throw "M3 Stage C blind patch could not locate backend log assignment; evidence capture cannot be guaranteed."
}
$UiText = $UiText.Replace($LogNeedle, $LogReplacement)

# V3 normally deletes its temporary backend log when the Control Surface closes.
# In Stage C that same variable now points at our evidence file, so suppress only
# that cleanup line while blind mode is active. Normal non-Stage-C cleanup is
# untouched because this patch returns early when there is no active session.
$CleanupNeedle = 'if ($script:BackendLogPath -and (Test-Path $script:BackendLogPath)) { Remove-Item $script:BackendLogPath -Force -ErrorAction SilentlyContinue }'
$CleanupReplacement = 'if ($script:BackendLogPath -and (Test-Path $script:BackendLogPath)) { Write-Host "[KADENCE STAGE C] Raw backend log retained: $script:BackendLogPath" }'
if (-not $UiText.Contains($CleanupNeedle)) {
    throw "M3 Stage C blind patch could not locate backend-log cleanup; evidence retention cannot be guaranteed."
}
$UiText = $UiText.Replace($CleanupNeedle, $CleanupReplacement)

return $UiText
