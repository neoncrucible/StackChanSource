param(
    [string]$RuntimeRoot = (Join-Path $PSScriptRoot ".runtime"),
    [string]$Model = "qwen3.5:4b",
    [string]$BaseUrl = "http://127.0.0.1:11434"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

if ($env:OS -ne "Windows_NT") {
    throw "Kadence LOCAL robot profile is currently Windows-only."
}

. (Join-Path $PSScriptRoot "kadence_local_common.ps1")

$RepoDir = Join-Path $RuntimeRoot "xiaozhi-esp32-server"
$ConfigPath = Join-Path $RepoDir "main\xiaozhi-server\data\.config.yaml"
$OllamaProvider = Join-Path $RepoDir "main\xiaozhi-server\core\providers\llm\ollama\ollama.py"
$LocalRuntimeRoot = Join-Path $RuntimeRoot "local"
$Utf8NoBom = [System.Text.UTF8Encoding]::new($false)

foreach ($RequiredPath in @($ConfigPath, $OllamaProvider)) {
    if (-not (Test-Path $RequiredPath)) {
        throw "Kadence LOCAL robot profile required path was not found: $RequiredPath"
    }
}

if ($BaseUrl.TrimEnd('/') -ne "http://127.0.0.1:11434") {
    throw "Kadence LOCAL robot profile only permits the Project-owned loopback Ollama endpoint http://127.0.0.1:11434."
}

$Persona = Get-KadenceCanonicalPersona
$Paths = Get-KadenceLocalPaths -RuntimeRoot $LocalRuntimeRoot
if (-not (Test-Path $Paths.PidPath) -or -not (Test-Path $Paths.StatePath)) {
    throw "Kadence LOCAL ownership state was not found. Run start_local_windows.ps1 first."
}

$State = Get-Content -LiteralPath $Paths.StatePath -Raw | ConvertFrom-Json
if ([string]$State.schema -ne "kadence.local-runtime.v1" -or
    [string]$State.engine -ne "LOCAL" -or
    [string]$State.provider -ne "ollama") {
    throw "Kadence LOCAL ownership state does not describe the accepted LOCAL Ollama runtime."
}
if ([string]$State.model -ne $Model) {
    throw "Kadence LOCAL runtime model '$($State.model)' does not match requested robot model '$Model'."
}
if ([string]$State.host -ne $script:KadenceLocalHost) {
    throw "Kadence LOCAL runtime host '$($State.host)' does not match $script:KadenceLocalHost."
}
if ([string]$State.canonical_persona_sha256 -ne $Persona.Sha256) {
    throw "Kadence LOCAL runtime persona hash does not match canonical persona v2."
}

$ProcessId = [int]$State.pid
$null = Assert-KadenceOwnedOllamaProcess -ProcessId $ProcessId -ExpectedExecutable ([string]$State.executable)
$Owners = @(Get-KadencePortOwners -Port 11434)
if ($Owners -notcontains $ProcessId) {
    throw "Recorded Kadence LOCAL PID $ProcessId does not own TCP 11434. Refusing robot startup."
}
if (-not (Test-KadenceOllamaApi)) {
    throw "Project-owned Ollama API is not ready on $script:KadenceLocalHost."
}

$Tags = Invoke-KadenceOllamaApi -Method Get -Path "tags" -TimeoutSec 10
$InstalledNames = @($Tags.models | ForEach-Object { [string]$_.name })
if ($InstalledNames -notcontains $Model) {
    throw "LOCAL model '$Model' is absent from the Project-owned model store."
}

$ConfigText = [System.IO.File]::ReadAllText($ConfigPath, $Utf8NoBom).Replace("`r`n", "`n")
$SelectedMatches = [regex]::Matches($ConfigText, '(?m)^  LLM:[ \t]+\S+[ \t]*$')
if ($SelectedMatches.Count -ne 1) {
    throw "Expected exactly one selected_module LLM line; found $($SelectedMatches.Count)."
}

$OllamaBlock = @"
  OllamaLLM:
    type: ollama
    model_name: "$Model"
    base_url: $($BaseUrl.TrimEnd('/'))
"@.Replace("`r`n", "`n")

$ExistingBlock = [regex]::Match(
    $ConfigText,
    '(?ms)^  OllamaLLM:[ \t]*\n(?<body>.*?)(?=^  \S|^\S|\z)'
)
if ($ExistingBlock.Success) {
    if ($ExistingBlock.Groups['body'].Value -notmatch '(?m)^    type:[ \t]+ollama[ \t]*$') {
        throw "Existing OllamaLLM block is not type=ollama; refusing to overwrite an unknown provider."
    }
    $ConfigText = $ConfigText.Remove($ExistingBlock.Index, $ExistingBlock.Length).Insert(
        $ExistingBlock.Index,
        $OllamaBlock + "`n"
    )
}
else {
    $TtsAnchor = [regex]::Match($ConfigText, '(?m)^TTS:[ \t]*$')
    if (-not $TtsAnchor.Success) {
        throw "Top-level TTS block was not found; refusing to guess where to add OllamaLLM."
    }
    $ConfigText = $ConfigText.Insert($TtsAnchor.Index, $OllamaBlock + "`n`n")
}

$ConfigText = [regex]::Replace(
    $ConfigText,
    '(?m)^  LLM:[ \t]+\S+[ \t]*$',
    '  LLM: OllamaLLM',
    1
)

$SelectedAfter = [regex]::Matches($ConfigText, '(?m)^  LLM:[ \t]+OllamaLLM[ \t]*$')
$BlocksAfter = [regex]::Matches($ConfigText, '(?m)^  OllamaLLM:[ \t]*$')
if ($SelectedAfter.Count -ne 1 -or $BlocksAfter.Count -ne 1) {
    throw "LOCAL robot profile post-write verification failed before runtime config write."
}
if ($ConfigText -notmatch ('(?m)^    model_name:[ \t]+"?' + [regex]::Escape($Model) + '"?[ \t]*$') -or
    $ConfigText -notmatch '(?m)^    base_url:[ \t]+http://127\.0\.0\.1:11434[ \t]*$') {
    throw "LOCAL robot model or loopback endpoint verification failed before runtime config write."
}

[System.IO.File]::WriteAllText(
    $ConfigPath,
    $ConfigText.Replace("`n", "`r`n"),
    $Utf8NoBom
)

Write-Host "Kadence robot cognition: LOCAL / Ollama / $Model"
Write-Host "Ollama endpoint: http://127.0.0.1:11434 (Project-owned PID $ProcessId)"
Write-Host "Canonical identity: v2 / sha256 $($Persona.Sha256)"
Write-Host "No LUNA cognition fallback is configured for this startup path."
