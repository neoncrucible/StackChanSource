param(
    [Parameter(Mandatory = $true)][string]$RepoDir
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

# Keep the pinned Xiaozhi checkout immutable in Git and make only narrowly
# guarded compatibility edits to the ignored local runtime.
$GeminiProvider = Join-Path $RepoDir "main\xiaozhi-server\core\providers\llm\gemini\gemini.py"
$SileroProvider = Join-Path $RepoDir "main\xiaozhi-server\core\providers\vad\silero.py"
$RuntimeConfig = Join-Path $RepoDir "main\xiaozhi-server\data\.config.yaml"
$TemplateConfig = Join-Path $PSScriptRoot "kadence.config.example.yaml"
$Utf8NoBom = [System.Text.UTF8Encoding]::new($false)

if (-not (Test-Path $GeminiProvider)) {
    throw "Pinned Xiaozhi Gemini provider was not found: $GeminiProvider"
}
if (-not (Test-Path $SileroProvider)) {
    throw "Pinned Xiaozhi Silero provider was not found: $SileroProvider"
}
if (-not (Test-Path $RuntimeConfig)) {
    throw "Pinned Xiaozhi runtime config was not found: $RuntimeConfig"
}
if (-not (Test-Path $TemplateConfig)) {
    throw "Kadence Alpha config template was not found: $TemplateConfig"
}

# Always read/write these files as UTF-8 explicitly. Windows PowerShell 5.1
# otherwise uses its legacy default text encoding and can corrupt non-ASCII
# punctuation in YAML comments during an in-place migration.
$ProviderText = [System.IO.File]::ReadAllText($GeminiProvider, $Utf8NoBom)
$ProviderChanged = $false

# google-generativeai==0.8.5 does not accept a top-level `timeout=` argument on
# GenerativeModel.generate_content(). Per-request transport settings belong in
# `request_options`.
$TimeoutOriginal = "            timeout=self.timeout,"
$TimeoutReplacement = '            request_options={"timeout": self.timeout},'
if ($ProviderText.Contains($TimeoutReplacement)) {
    Write-Host "Xiaozhi Gemini timeout compatibility patch: already applied."
}
elseif ($ProviderText.Contains($TimeoutOriginal)) {
    $ProviderText = $ProviderText.Replace($TimeoutOriginal, $TimeoutReplacement)
    $ProviderChanged = $true
    Write-Host "Applied Xiaozhi Gemini compatibility patch: timeout -> request_options.timeout"
}
else {
    throw "Gemini timeout compatibility patch guard failed. Expected pinned call was not found; refusing to modify runtime."
}

# Gemini 3.x deprecates the legacy sampling parameters used by this pinned
# provider. Keep only the output-token ceiling for the Alpha 1 smoke test.
$SamplingOriginal = @"
        self.gen_cfg = GenerationConfig(
            temperature=0.7,
            top_p=0.9,
            top_k=40,
            max_output_tokens=2048,
        )
"@
$SamplingReplacement = @"
        self.gen_cfg = GenerationConfig(
            max_output_tokens=2048,
        )
"@

if ($ProviderText.Contains($SamplingReplacement)) {
    Write-Host "Xiaozhi Gemini 3.x generation-config patch: already applied."
}
elseif ($ProviderText.Contains($SamplingOriginal)) {
    $ProviderText = $ProviderText.Replace($SamplingOriginal, $SamplingReplacement)
    $ProviderChanged = $true
    Write-Host "Applied Xiaozhi Gemini 3.x generation-config patch: removed deprecated sampling parameters."
}
else {
    throw "Gemini generation-config patch guard failed. Expected pinned GenerationConfig block was not found; refusing to modify runtime."
}

if ($ProviderChanged) {
    [System.IO.File]::WriteAllText($GeminiProvider, $ProviderText, $Utf8NoBom)
}

$ConfigText = [System.IO.File]::ReadAllText($RuntimeConfig, $Utf8NoBom)

# Repair the specific Windows encoding failure seen during Alpha 1 migration.
# Preserve the two already-entered credentials locally, rebuild from the clean
# checked-in template, and never print either secret.
$IllegalYamlControls = '[\x00-\x08\x0B\x0C\x0E-\x1F\x7F-\x9F]'
if ([regex]::IsMatch($ConfigText, $IllegalYamlControls)) {
    $ApiKeys = [regex]::Matches(
        $ConfigText,
        '(?m)^[ \t]+api_key:[ \t]*(.+?)[ \t]*$'
    )
    if ($ApiKeys.Count -ne 2) {
        throw "Runtime YAML is encoding-corrupted and its two API keys could not be recovered safely. Refusing to overwrite it."
    }

    $OpenAiKey = $ApiKeys[0].Groups[1].Value.Trim()
    $GeminiKey = $ApiKeys[1].Groups[1].Value.Trim()
    if ([string]::IsNullOrWhiteSpace($OpenAiKey) -or
        [string]::IsNullOrWhiteSpace($GeminiKey)) {
        throw "Runtime YAML is encoding-corrupted and one recovered API key was empty. Refusing to overwrite it."
    }

    $TemplateText = [System.IO.File]::ReadAllText($TemplateConfig, $Utf8NoBom)
    $ConfigText = $TemplateText.Replace("REPLACE_WITH_OPENAI_API_KEY", $OpenAiKey)
    $ConfigText = $ConfigText.Replace("REPLACE_WITH_GEMINI_API_KEY", $GeminiKey)
    [System.IO.File]::WriteAllText($RuntimeConfig, $ConfigText, $Utf8NoBom)
    Write-Host "Repaired Alpha runtime YAML encoding from clean template; existing API keys preserved locally."
}

# Alpha 1 is a latency baseline. Gemini 3.6 Flash defaults to medium thinking,
# which can exceed the robot's 30-second response watchdog. Flash-Lite defaults
# to minimal thinking and is the better baseline for spoken turn latency.
$RetiredModel = '    model_name: "gemini-2.0-flash"'
$SlowModel = '    model_name: "gemini-3.6-flash"'
$TargetModel = '    model_name: "gemini-3.5-flash-lite"'

if ($ConfigText.Contains($TargetModel)) {
    Write-Host "Kadence Gemini model: gemini-3.5-flash-lite already configured."
}
elseif ($ConfigText.Contains($SlowModel)) {
    $ConfigText = $ConfigText.Replace($SlowModel, $TargetModel)
    [System.IO.File]::WriteAllText($RuntimeConfig, $ConfigText, $Utf8NoBom)
    Write-Host "Migrated Kadence Gemini model: gemini-3.6-flash -> gemini-3.5-flash-lite"
}
elseif ($ConfigText.Contains($RetiredModel)) {
    $ConfigText = $ConfigText.Replace($RetiredModel, $TargetModel)
    [System.IO.File]::WriteAllText($RuntimeConfig, $ConfigText, $Utf8NoBom)
    Write-Host "Migrated Kadence Gemini model: gemini-2.0-flash -> gemini-3.5-flash-lite"
}
else {
    throw "Gemini model migration guard failed. Expected an Alpha model line was not found; refusing to modify runtime config."
}

# Xiaozhi intentionally bypasses Silero VAD in manual-listen mode by returning
# True for every PCM frame. Kadence Alpha currently uses manual mode because the
# robot owns end-of-speech. For diagnosis only, still run the pinned Silero model
# and log its SPEECH/SILENCE edges, but continue returning True so ASR buffering
# and the robot-controlled stop message behave exactly as before.
$VadText = [System.IO.File]::ReadAllText($SileroProvider, $Utf8NoBom)
$VadManualOriginal = @'
    def is_vad(self, conn, pcm_frame):
        # 手动模式：直接返回True，不进行实时VAD检测，所有音频都缓存
        if conn.client_listen_mode == "manual":
            return True

        try:
'@
$VadManualReplacement = @'
    def is_vad(self, conn, pcm_frame):
        # Kadence Alpha diagnostic mode: manual capture still buffers every frame,
        # but Silero also runs so we can compare its endpoint with the ESP32 VAD.
        kadence_manual_diagnostics = conn.client_listen_mode == "manual"

        try:
'@
$VadReturnOriginal = @'
            return client_have_voice
        except Exception as e:
'@
$VadReturnReplacement = @'
            if kadence_manual_diagnostics:
                previous = getattr(conn, "_kadence_diag_vad_state", None)
                if previous is None or previous != client_have_voice:
                    logger.bind(tag=TAG).info(
                        f"KADENCE SERVER VAD: {'SPEECH' if client_have_voice else 'SILENCE'}"
                    )
                    conn._kadence_diag_vad_state = client_have_voice
                return True
            return client_have_voice
        except Exception as e:
'@

# The main repo and the pinned runtime are separate Git checkouts. On Windows
# one may be CRLF while the other remains LF, so normalise all comparison text
# before applying the guarded replacements.
$VadText = $VadText.Replace("`r`n", "`n")
$VadManualOriginal = $VadManualOriginal.Replace("`r`n", "`n")
$VadManualReplacement = $VadManualReplacement.Replace("`r`n", "`n")
$VadReturnOriginal = $VadReturnOriginal.Replace("`r`n", "`n")
$VadReturnReplacement = $VadReturnReplacement.Replace("`r`n", "`n")

$VadChanged = $false
if ($VadText.Contains($VadManualReplacement)) {
    Write-Host "Kadence manual-mode Silero diagnostics: already applied."
}
elseif ($VadText.Contains($VadManualOriginal)) {
    $VadText = $VadText.Replace($VadManualOriginal, $VadManualReplacement)
    $VadChanged = $true
} else {
    throw "Silero diagnostic patch guard failed at manual-mode bypass; refusing to modify runtime."
}

if ($VadText.Contains($VadReturnReplacement)) {
    Write-Host "Kadence server VAD edge logger: already applied."
}
elseif ($VadText.Contains($VadReturnOriginal)) {
    $VadText = $VadText.Replace($VadReturnOriginal, $VadReturnReplacement)
    $VadChanged = $true
} else {
    throw "Silero diagnostic patch guard failed at VAD return; refusing to modify runtime."
}

if ($VadChanged) {
    [System.IO.File]::WriteAllText($SileroProvider, $VadText, $Utf8NoBom)
    Write-Host "Applied Kadence manual-mode Silero endpoint diagnostics (buffering semantics unchanged)."
}
