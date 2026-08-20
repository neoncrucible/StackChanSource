param(
    [Parameter(Mandatory = $true)][string]$RepoDir
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

# Keep the pinned Xiaozhi checkout immutable in Git and make only narrowly
# guarded compatibility edits to the ignored local runtime.
$GeminiProvider = Join-Path $RepoDir "main\xiaozhi-server\core\providers\llm\gemini\gemini.py"
$RuntimeConfig = Join-Path $RepoDir "main\xiaozhi-server\data\.config.yaml"

if (-not (Test-Path $GeminiProvider)) {
    throw "Pinned Xiaozhi Gemini provider was not found: $GeminiProvider"
}
if (-not (Test-Path $RuntimeConfig)) {
    throw "Pinned Xiaozhi runtime config was not found: $RuntimeConfig"
}

$ProviderText = Get-Content -Raw $GeminiProvider
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
    [System.IO.File]::WriteAllText(
        $GeminiProvider,
        $ProviderText,
        [System.Text.UTF8Encoding]::new($false)
    )
}

# Alpha 1 is a latency baseline. Gemini 3.6 Flash defaults to medium thinking,
# which can exceed the robot's 30-second response watchdog. Flash-Lite defaults
# to minimal thinking and is the better baseline for spoken turn latency.
$ConfigText = Get-Content -Raw $RuntimeConfig
$RetiredModel = '    model_name: "gemini-2.0-flash"'
$SlowModel = '    model_name: "gemini-3.6-flash"'
$TargetModel = '    model_name: "gemini-3.5-flash-lite"'

if ($ConfigText.Contains($TargetModel)) {
    Write-Host "Kadence Gemini model: gemini-3.5-flash-lite already configured."
}
elseif ($ConfigText.Contains($SlowModel)) {
    $ConfigText = $ConfigText.Replace($SlowModel, $TargetModel)
    [System.IO.File]::WriteAllText(
        $RuntimeConfig,
        $ConfigText,
        [System.Text.UTF8Encoding]::new($false)
    )
    Write-Host "Migrated Kadence Gemini model: gemini-3.6-flash -> gemini-3.5-flash-lite"
}
elseif ($ConfigText.Contains($RetiredModel)) {
    $ConfigText = $ConfigText.Replace($RetiredModel, $TargetModel)
    [System.IO.File]::WriteAllText(
        $RuntimeConfig,
        $ConfigText,
        [System.Text.UTF8Encoding]::new($false)
    )
    Write-Host "Migrated Kadence Gemini model: gemini-2.0-flash -> gemini-3.5-flash-lite"
}
else {
    throw "Gemini model migration guard failed. Expected an Alpha model line was not found; refusing to modify runtime config."
}
