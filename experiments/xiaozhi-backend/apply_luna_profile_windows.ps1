param(
    [string]$RuntimeRoot = (Join-Path $PSScriptRoot ".runtime")
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$RepoDir = Join-Path $RuntimeRoot "xiaozhi-esp32-server"
$ConfigPath = Join-Path $RepoDir "main\xiaozhi-server\data\.config.yaml"
$OpenAiProvider = Join-Path $RepoDir "main\xiaozhi-server\core\providers\llm\openai\openai.py"
$Utf8NoBom = [System.Text.UTF8Encoding]::new($false)

if (-not (Test-Path $ConfigPath)) {
    throw "Runtime config not found: $ConfigPath"
}
if (-not (Test-Path $OpenAiProvider)) {
    throw "Pinned Xiaozhi OpenAI LLM provider was not found: $OpenAiProvider"
}

function Get-RealtimeOpenAiKeyLine {
    param([string]$ConfigText)

    $Block = [regex]::Match(
        $ConfigText,
        '(?ms)^  OpenaiRealtimeASR:\s*\r?\n(?<body>.*?)(?=^  \S|\z)'
    )
    if (-not $Block.Success) {
        throw "OpenaiRealtimeASR config block was not found; refusing to invent an OpenAI credential source."
    }

    $Key = [regex]::Match($Block.Groups['body'].Value, '(?m)^    api_key:\s*(.+?)\s*$')
    if (-not $Key.Success -or [string]::IsNullOrWhiteSpace($Key.Groups[1].Value)) {
        throw "OpenaiRealtimeASR api_key line was not found or was empty."
    }

    return $Key.Groups[1].Value.Trim()
}

function Ensure-LunaProviderCompatibility {
    $Text = [System.IO.File]::ReadAllText($OpenAiProvider, $Utf8NoBom).Replace("`r`n", "`n")
    $Changed = $false

    $BrokenReasoningProperty = '            self.base_url = config.get("url")        self.reasoning_effort = config.get("reasoning_effort")'
    $RepairedReasoningProperty = '            self.base_url = config.get("url")' + "`n" + '        self.reasoning_effort = config.get("reasoning_effort")'
    if ($Text.Contains($BrokenReasoningProperty)) {
        $Text = $Text.Replace($BrokenReasoningProperty, $RepairedReasoningProperty)
        $Changed = $true
        Write-Host "Repaired Alpha 2 OpenAI reasoning patch newline."
    }

    $ReasoningProperty = '        self.reasoning_effort = config.get("reasoning_effort")'
    if (-not $Text.Contains($ReasoningProperty)) {
        $BaseUrlAnchor = '        else:' + "`n" + '            self.base_url = config.get("url")'
        if (-not $Text.Contains($BaseUrlAnchor)) {
            throw "OpenAI reasoning compatibility patch guard failed at provider configuration."
        }
        $Text = $Text.Replace($BaseUrlAnchor, $BaseUrlAnchor + "`n" + $ReasoningProperty)
        $Changed = $true
    }

    $ReasoningRequest = '        if self.reasoning_effort not in (None, ""):' + "`n" +
        '            request_params["reasoning_effort"] = self.reasoning_effort' + "`n`n"
    $RequestAnchor = '        self._apply_thinking_disabled(request_params)'
    $ExistingRequestCount = ([regex]::Matches(
        $Text,
        [regex]::Escape('request_params["reasoning_effort"] = self.reasoning_effort')
    )).Count

    if ($ExistingRequestCount -eq 0) {
        $AnchorCount = ([regex]::Matches($Text, [regex]::Escape($RequestAnchor))).Count
        if ($AnchorCount -ne 2) {
            throw "OpenAI reasoning compatibility patch guard expected two request sites; found $AnchorCount."
        }
        $Text = $Text.Replace($RequestAnchor, $ReasoningRequest + $RequestAnchor)
        $Changed = $true
    }
    elseif ($ExistingRequestCount -ne 2) {
        throw "OpenAI reasoning compatibility patch is only partially applied; refusing to continue."
    }

    if (-not $Text.Contains($ReasoningProperty) -or $Text.Contains($BrokenReasoningProperty)) {
        throw "OpenAI reasoning compatibility post-patch verification failed."
    }

    $FinalRequestCount = ([regex]::Matches(
        $Text,
        [regex]::Escape('request_params["reasoning_effort"] = self.reasoning_effort')
    )).Count
    if ($FinalRequestCount -ne 2) {
        throw "OpenAI reasoning request post-patch verification failed."
    }

    if ($Changed) {
        [System.IO.File]::WriteAllText($OpenAiProvider, $Text, $Utf8NoBom)
        Write-Host "Installed Alpha 2 OpenAI reasoning-effort compatibility patch."
    }
    else {
        Write-Host "Alpha 2 OpenAI reasoning-effort compatibility patch: already applied."
    }
}

Ensure-LunaProviderCompatibility

$ConfigText = [System.IO.File]::ReadAllText($ConfigPath, $Utf8NoBom)
$SelectedMatches = [regex]::Matches($ConfigText, '(?m)^  LLM:\s+\S+\s*$')
if ($SelectedMatches.Count -ne 1) {
    throw "Expected exactly one selected_module LLM line; found $($SelectedMatches.Count)."
}

$OpenAiKeyLine = Get-RealtimeOpenAiKeyLine -ConfigText $ConfigText
$LunaBlock = @"
  OpenAILLM:
    type: openai
    api_key: $OpenAiKeyLine
    base_url: https://api.openai.com/v1
    model_name: "gpt-5.6-luna"
    reasoning_effort: "none"
"@

if ($ConfigText -notmatch '(?m)^  OpenAILLM:\s*$') {
    $Tts = [regex]::Match($ConfigText, '(?m)^TTS:\s*$')
    if (-not $Tts.Success) {
        throw "Top-level TTS block was not found; refusing to guess where to add the Luna profile."
    }
    $ConfigText = $ConfigText.Insert($Tts.Index, $LunaBlock + "`r`n")
}
else {
    if ($ConfigText -notmatch '(?m)^    model_name:\s*"?gpt-5\.6-luna"?\s*$') {
        throw "Existing OpenAILLM block does not target gpt-5.6-luna; refusing to overwrite an unknown local profile."
    }
    if ($ConfigText -notmatch '(?m)^    reasoning_effort:\s*"?none"?\s*$') {
        throw "Existing OpenAILLM block does not use reasoning_effort=none; refusing to silently alter the accepted profile."
    }
}

$ConfigText = [regex]::Replace(
    $ConfigText,
    '(?m)^  LLM:\s+\S+\s*$',
    '  LLM: OpenAILLM',
    1
)

# Retire Kadence-owned Gemini configuration while leaving the pinned upstream
# provider source untouched for provenance. The runtime no longer advertises or
# configures Gemini after M5.
$ConfigText = [regex]::Replace(
    $ConfigText.Replace("`r`n", "`n"),
    '(?ms)^  GeminiLLM:\s*\n.*?(?=^  \S|^\S|\z)',
    ''
).Replace("`n", "`r`n")

[System.IO.File]::WriteAllText($ConfigPath, $ConfigText, $Utf8NoBom)
Write-Host "Kadence LLM profile: openai-luna / model=gpt-5.6-luna / reasoning=none"
Write-Host "Kadence Gemini runtime profile: retired after M5."
