param(
    [string]$RuntimeRoot = (Join-Path $PSScriptRoot ".runtime")
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$PinnedCommit = "e1876f1ce19cad6e7bfd7c80e41dc56b2e858dd5"
$RepoDir = Join-Path $RuntimeRoot "xiaozhi-esp32-server"
$ProviderSource = Join-Path $PSScriptRoot "kadence_ollama_provider.py"
$ProviderTarget = Join-Path $RepoDir "main\xiaozhi-server\core\providers\llm\ollama\ollama.py"
$TtsBase = Join-Path $RepoDir "main\xiaozhi-server\core\providers\tts\base.py"
$Utf8NoBom = [System.Text.UTF8Encoding]::new($false)

foreach ($RequiredPath in @($RepoDir, $ProviderSource, $ProviderTarget, $TtsBase)) {
    if (-not (Test-Path $RequiredPath)) {
        throw "Kadence LOCAL robot runtime required path was not found: $RequiredPath"
    }
}

$ActualCommit = (git -C $RepoDir rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $ActualCommit -ne $PinnedCommit) {
    throw "LOCAL robot runtime is not the pinned Xiaozhi revision $PinnedCommit."
}

$ProviderText = [System.IO.File]::ReadAllText($ProviderTarget, $Utf8NoBom).Replace("`r`n", "`n")
$ProviderSourceText = [System.IO.File]::ReadAllText($ProviderSource, $Utf8NoBom).Replace("`r`n", "`n")
if ($ProviderText -ne $ProviderSourceText) {
    $KnownKadenceProvider = $ProviderText.Contains(
        'Project-owned LOCAL Ollama adapter for Kadence robot voice turns.'
    )
    if (-not $KnownKadenceProvider) {
        foreach ($UpstreamMarker in @(
            'class LLMProvider(LLMProviderBase):',
            'self.client = OpenAI(',
            'dialogue_copy = dialogue.copy()',
            'model=self.model_name, messages=dialogue, stream=True',
            'def response_with_functions(self, session_id, dialogue, functions=None):'
        )) {
            if (-not $ProviderText.Contains($UpstreamMarker)) {
                throw "Pinned Ollama provider guard failed at marker: $UpstreamMarker"
            }
        }
    }
    [System.IO.File]::WriteAllText($ProviderTarget, $ProviderSourceText, $Utf8NoBom)
    Write-Host "Installed Kadence LOCAL English/voice Ollama adapter into ignored runtime."
}
else {
    Write-Host "Kadence LOCAL English/voice Ollama adapter: already installed."
}

$TtsText = [System.IO.File]::ReadAllText($TtsBase, $Utf8NoBom).Replace("`r`n", "`n")
$TtsChanged = $false

$SegmentLimitOriginal = @'
        self.processed_chars = 0
        self.is_first_sentence = True
'@.Replace("`r`n", "`n")
$SegmentLimitPatched = @'
        self.processed_chars = 0
        self.is_first_sentence = True
        # KADENCE ENGLISH TTS SEGMENTATION: keep individual robot playback
        # payloads below the physically observed long-segment failure range.
        self.kadence_max_segment_chars = 140
'@.Replace("`r`n", "`n")

if ($TtsText.Contains($SegmentLimitPatched)) {
    Write-Host "Kadence TTS segment-length guard: already applied."
}
elseif ($TtsText.Contains($SegmentLimitOriginal)) {
    $TtsText = $TtsText.Replace($SegmentLimitOriginal, $SegmentLimitPatched)
    $TtsChanged = $true
    Write-Host "Applied Kadence 140-character TTS segment-length guard."
}
else {
    throw "Kadence TTS segment-length patch guard failed."
}

$TextLoopOriginal = @'
                    segment_text = self._get_segment_text()
                    if segment_text:
                        self.to_tts_stream(segment_text, opus_handler=self.handle_opus)
'@.Replace("`r`n", "`n")
$TextLoopPatched = @'
                    while True:
                        segment_text = self._get_segment_text()
                        if not segment_text:
                            break
                        self.to_tts_stream(segment_text, opus_handler=self.handle_opus)
'@.Replace("`r`n", "`n")

if ($TtsText.Contains($TextLoopPatched)) {
    Write-Host "Kadence TTS multi-segment drain: already applied."
}
elseif ($TtsText.Contains($TextLoopOriginal)) {
    $TtsText = $TtsText.Replace($TextLoopOriginal, $TextLoopPatched)
    $TtsChanged = $true
    Write-Host "Applied Kadence TTS multi-segment drain."
}
else {
    throw "Kadence TTS multi-segment patch guard failed."
}

$MethodStart = $TtsText.IndexOf("    def _get_segment_text(self):`n")
$MethodEnd = $TtsText.IndexOf("    def _process_audio_file_stream(`n", $MethodStart)
if ($MethodStart -lt 0 -or $MethodEnd -le $MethodStart) {
    throw "Kadence TTS segmenter method anchors were not found."
}

$ExistingMethod = $TtsText.Substring($MethodStart, $MethodEnd - $MethodStart)
$PatchedMethod = @'
    def _get_segment_text(self):
        # KADENCE ENGLISH TTS SEGMENTATION: the pinned upstream list omitted
        # ASCII full stop/colon/newline and could emit a 296-character English
        # paragraph as one robot audio payload.
        full_text = "".join(self.tts_text_buff)
        while True:
            current_text = full_text[self.processed_chars :]
            if not current_text:
                return None

            punctuations_to_use = set(
                self.first_sentence_punctuations
                if self.is_first_sentence
                else self.punctuations
            )
            punctuations_to_use.update((".", ":", "\n"))

            punctuation_end = None
            for index, char in enumerate(current_text):
                if char not in punctuations_to_use:
                    continue
                # Keep an ellipsis together instead of producing three tiny
                # TTS requests.
                if char == "." and (
                    (index > 0 and current_text[index - 1] == ".")
                    or (
                        index + 1 < len(current_text)
                        and current_text[index + 1] == "."
                    )
                ):
                    continue
                punctuation_end = index + 1
                break

            max_chars = self.kadence_max_segment_chars
            if punctuation_end is not None and punctuation_end <= max_chars:
                split_at = punctuation_end
            elif len(current_text) >= max_chars:
                split_at = current_text.rfind(" ", 0, max_chars + 1)
                if split_at < max_chars // 2:
                    split_at = max_chars
                else:
                    split_at += 1
            elif self.tts_stop_request:
                split_at = len(current_text)
            else:
                return None

            segment_text_raw = current_text[:split_at]
            segment_text = textUtils.get_string_no_punctuation_or_emoji(
                segment_text_raw
            )
            self.processed_chars += len(segment_text_raw)
            self.is_first_sentence = False
            if segment_text:
                return segment_text

'@.Replace("`r`n", "`n")

if ($ExistingMethod.Contains(
        '# KADENCE ENGLISH TTS SEGMENTATION: the pinned upstream list omitted'
    )) {
    Write-Host "Kadence English TTS segmenter: already applied."
}
elseif ($ExistingMethod.Contains('        last_punct_pos = -1') -and
        $ExistingMethod.Contains('        for punct in punctuations_to_use:') -and
        $ExistingMethod.Contains('            self.first_sentence_punctuations') -and
        $ExistingMethod.Contains('            return segment_text')) {
    $TtsText = $TtsText.Remove($MethodStart, $MethodEnd - $MethodStart).Insert(
        $MethodStart,
        $PatchedMethod
    )
    $TtsChanged = $true
    Write-Host "Applied Kadence English punctuation and bounded TTS segmenter."
}
else {
    throw "Kadence TTS segmenter guard found an unknown runtime implementation."
}

foreach ($RequiredMarker in @(
    'self.kadence_max_segment_chars = 140',
    'while True:',
    'punctuations_to_use.update((".", ":", "\n"))',
    'elif len(current_text) >= max_chars:'
)) {
    if (-not $TtsText.Contains($RequiredMarker)) {
        throw "Kadence TTS post-patch verification failed at marker: $RequiredMarker"
    }
}

if ($TtsChanged) {
    [System.IO.File]::WriteAllText($TtsBase, $TtsText, $Utf8NoBom)
}

Write-Host "Kadence LOCAL robot runtime compatibility ready: English voice guard / bounded TTS chunks."
