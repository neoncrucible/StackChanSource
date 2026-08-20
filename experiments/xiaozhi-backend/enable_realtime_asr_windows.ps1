param(
    [string]$RuntimeRoot = (Join-Path $PSScriptRoot ".runtime")
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$PinnedCommit = "e1876f1ce19cad6e7bfd7c80e41dc56b2e858dd5"
$RepoDir = Join-Path $RuntimeRoot "xiaozhi-esp32-server"
$ServerDir = Join-Path $RepoDir "main\xiaozhi-server"
$ConfigPath = Join-Path $ServerDir "data\.config.yaml"
$ProviderSource = Join-Path $PSScriptRoot "openai_realtime_asr.py"
$ProviderTarget = Join-Path $ServerDir "core\providers\asr\openai_realtime.py"
$BackupPath = "$ConfigPath.pre-realtime-asr.bak"
$Utf8NoBom = [System.Text.UTF8Encoding]::new($false)
$EndpointSilenceMs = 700

if (-not (Test-Path $RepoDir)) {
    throw "Xiaozhi runtime not found. Run bootstrap_windows.ps1 first."
}
if (-not (Test-Path $ConfigPath)) {
    throw "Runtime config not found: $ConfigPath"
}
if (-not (Test-Path $ProviderSource)) {
    throw "Tracked Kadence Realtime ASR provider not found: $ProviderSource"
}

$ActualCommit = (git -C $RepoDir rev-parse HEAD).Trim()
if ($ActualCommit -ne $PinnedCommit) {
    throw "Runtime is not on the Alpha 1 pinned commit. Expected $PinnedCommit, got $ActualCommit"
}

$ProviderText = [System.IO.File]::ReadAllText($ProviderSource, $Utf8NoBom)
if (-not $ProviderText.Contains("class ASRProvider")) {
    throw "Realtime ASR provider safety check failed: ASRProvider class not found."
}
if (-not $ProviderText.Contains("gpt-realtime-whisper")) {
    throw "Realtime ASR provider safety check failed: expected model marker not found."
}
if (-not $ProviderText.Contains('"type": "kadence"') -or
    -not $ProviderText.Contains('"event": "endpoint"')) {
    throw "Realtime ASR provider safety check failed: Kadence endpoint control marker not found."
}

$ExistingProvider = ""
if (Test-Path $ProviderTarget) {
    $ExistingProvider = [System.IO.File]::ReadAllText($ProviderTarget, $Utf8NoBom)
}
if ($ExistingProvider -ne $ProviderText) {
    [System.IO.File]::WriteAllText($ProviderTarget, $ProviderText, $Utf8NoBom)
    Write-Host "Installed Kadence OpenAI Realtime ASR provider into ignored Xiaozhi runtime."
}
else {
    Write-Host "Kadence OpenAI Realtime ASR provider: already installed."
}

$ConfigText = [System.IO.File]::ReadAllText($ConfigPath, $Utf8NoBom).Replace("`r`n", "`n")
$RealtimeSelected = '  ASR: OpenaiRealtimeASR'
$BatchSelected = '  ASR: OpenaiASR'
$EndpointLine = "    endpoint_silence_ms: $EndpointSilenceMs"
$EndpointPattern = '(?m)^    endpoint_silence_ms:[ \t]*\d+[ \t]*$'

if ($ConfigText.Contains($RealtimeSelected)) {
    if (-not $ConfigText.Contains('    type: openai_realtime') -or
        -not $ConfigText.Contains('    model_name: gpt-realtime-whisper')) {
        throw "Realtime ASR is selected but its config block is not the expected Alpha shape."
    }

    $ConfigChanged = $false
    if ([regex]::IsMatch($ConfigText, $EndpointPattern)) {
        $UpdatedConfig = [regex]::Replace(
            $ConfigText,
            $EndpointPattern,
            $EndpointLine,
            1
        )
        if ($UpdatedConfig -ne $ConfigText) {
            $ConfigText = $UpdatedConfig
            $ConfigChanged = $true
        }
    }
    else {
        $NoiseReductionLine = "    noise_reduction: far_field`n"
        if (-not $ConfigText.Contains($NoiseReductionLine)) {
            throw "Realtime ASR endpoint migration guard failed: noise_reduction line not found."
        }
        $ConfigText = $ConfigText.Replace(
            $NoiseReductionLine,
            "$NoiseReductionLine$EndpointLine`n"
        )
        $ConfigChanged = $true
    }

    if ([regex]::Matches($ConfigText, $EndpointPattern).Count -ne 1 -or
        -not $ConfigText.Contains($EndpointLine)) {
        throw "Realtime ASR endpoint migration verification failed; expected exactly one 700 ms endpoint setting."
    }

    if ($ConfigChanged) {
        [System.IO.File]::WriteAllText($ConfigPath, $ConfigText, $Utf8NoBom)
        Write-Host "Pinned Kadence server endpoint silence hold at ${EndpointSilenceMs} ms."
    }
    else {
        Write-Host "Kadence server endpoint silence hold: ${EndpointSilenceMs} ms."
    }

    Write-Host "Kadence ASR config: OpenAI Realtime already selected."
    return
}

if (-not $ConfigText.Contains($BatchSelected)) {
    throw "ASR migration guard failed: neither proven batch nor expected Realtime Alpha ASR is selected."
}

$BatchPattern = '(?ms)^ASR:\n  OpenaiASR:\n    type: openai\n    api_key:[ \t]*(?<key>[^\n]+)\n    base_url: https://api\.openai\.com/v1/audio/transcriptions\n    model_name: gpt-4o-mini-transcribe\n    output_dir: tmp/\n'
$Match = [regex]::Match($ConfigText, $BatchPattern)
if (-not $Match.Success) {
    throw "ASR migration guard failed: expected proven OpenaiASR block was not found."
}

$OpenAiKey = $Match.Groups['key'].Value.Trim()
if ([string]::IsNullOrWhiteSpace($OpenAiKey) -or
    $OpenAiKey -eq 'REPLACE_WITH_OPENAI_API_KEY') {
    throw "ASR migration guard failed: existing OpenAI API key is missing or unresolved."
}

if (-not (Test-Path $BackupPath)) {
    Copy-Item -LiteralPath $ConfigPath -Destination $BackupPath
    Write-Host "Saved local batch-ASR rollback config: $BackupPath"
}

$RealtimeBlock = @"
ASR:
  OpenaiRealtimeASR:
    type: openai_realtime
    api_key: $OpenAiKey
    ws_url: "wss://api.openai.com/v1/realtime?intent=transcription"
    model_name: gpt-realtime-whisper
    language: en
    noise_reduction: far_field
    endpoint_silence_ms: $EndpointSilenceMs
"@.Replace("`r`n", "`n")

$ConfigText = $ConfigText.Replace($BatchSelected, $RealtimeSelected)
$ConfigText = [regex]::Replace($ConfigText, $BatchPattern, $RealtimeBlock, 1)

if (-not $ConfigText.Contains($RealtimeSelected) -or
    -not $ConfigText.Contains('    type: openai_realtime') -or
    -not $ConfigText.Contains('    model_name: gpt-realtime-whisper') -or
    [regex]::Matches($ConfigText, $EndpointPattern).Count -ne 1 -or
    -not $ConfigText.Contains($EndpointLine)) {
    throw "Realtime ASR post-migration verification failed; refusing to write config."
}

[System.IO.File]::WriteAllText($ConfigPath, $ConfigText, $Utf8NoBom)
Write-Host "Migrated Kadence Alpha ASR: batch gpt-4o-mini-transcribe -> streaming gpt-realtime-whisper."
Write-Host "Pinned Kadence server endpoint silence hold at ${EndpointSilenceMs} ms."
Write-Host "Existing OpenAI API key preserved locally."
