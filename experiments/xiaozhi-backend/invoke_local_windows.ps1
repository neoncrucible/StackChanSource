param(
    [Parameter(Mandatory = $true)][string]$Prompt,
    [string]$RuntimeRoot = (Join-Path $PSScriptRoot ".runtime\local"),
    [double]$Temperature = 0.6,
    [double]$TopP = 0.9,
    [int]$MaxTokens = 220
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

if ($env:OS -ne "Windows_NT") {
    throw "Kadence LOCAL inference is currently Windows-only."
}

. (Join-Path $PSScriptRoot "kadence_local_common.ps1")

$Paths = Get-KadenceLocalPaths -RuntimeRoot $RuntimeRoot
if (-not (Test-Path $Paths.StatePath) -or -not (Test-Path $Paths.PidPath)) {
    throw "Kadence LOCAL runtime state was not found. Run start_local_windows.ps1 first."
}

$State = Get-Content $Paths.StatePath -Raw | ConvertFrom-Json
$ProcessId = [int]$State.pid
$null = Assert-KadenceOwnedOllamaProcess -ProcessId $ProcessId -ExpectedExecutable ([string]$State.executable)

$Owners = @(Get-KadencePortOwners -Port 11434)
if ($Owners -notcontains $ProcessId) {
    throw "Kadence LOCAL PID $ProcessId does not own TCP 11434. Refusing to send the prompt."
}
if (-not (Test-KadenceOllamaApi)) {
    throw "Kadence LOCAL Ollama API is not responding."
}

$Persona = Get-KadenceCanonicalPersona
if ([string]$State.canonical_persona_sha256 -ne $Persona.Sha256) {
    throw "Runtime identity state does not match the current canonical persona SHA. Restart LOCAL before prompting."
}

$Body = [ordered]@{
    model = [string]$State.model
    messages = @(
        [ordered]@{ role = "system"; content = $Persona.Text },
        [ordered]@{ role = "user"; content = $Prompt }
    )
    stream = $false
    think = $false
    keep_alive = -1
    options = [ordered]@{
        num_ctx = [int]$State.context_length
        temperature = $Temperature
        top_p = $TopP
        num_predict = $MaxTokens
    }
}

$Wall = [System.Diagnostics.Stopwatch]::StartNew()
$Response = Invoke-KadenceOllamaApi -Method Post -Path "chat" -Body $Body -TimeoutSec 300
$Wall.Stop()

$Text = [string]$Response.message.content
if ([string]::IsNullOrWhiteSpace($Text)) {
    throw "LOCAL model returned an empty response."
}

$EvalSeconds = [double]$Response.eval_duration / 1000000000.0
$TokensPerSecond = if ($EvalSeconds -gt 0 -and $null -ne $Response.eval_count) {
    [Math]::Round(([double]$Response.eval_count / $EvalSeconds), 2)
} else {
    0
}

Write-Host ""
Write-Host "KADENCE LOCAL [$($State.model)]"
Write-Host $Text.Trim()
Write-Host ""
Write-Host ("[metrics] wall={0:N0} ms total={1:N0} ms load={2:N0} ms prompt_tokens={3} eval_tokens={4} eval={5:N2} tok/s" -f `
    $Wall.Elapsed.TotalMilliseconds,
    ([double]$Response.total_duration / 1000000.0),
    ([double]$Response.load_duration / 1000000.0),
    $Response.prompt_eval_count,
    $Response.eval_count,
    $TokensPerSecond
)

[pscustomobject]@{
    Model = [string]$State.model
    Prompt = $Prompt
    Response = $Text.Trim()
    WallMilliseconds = [Math]::Round($Wall.Elapsed.TotalMilliseconds, 1)
    TotalMilliseconds = [Math]::Round(([double]$Response.total_duration / 1000000.0), 1)
    LoadMilliseconds = [Math]::Round(([double]$Response.load_duration / 1000000.0), 1)
    PromptTokens = [int]$Response.prompt_eval_count
    EvalTokens = [int]$Response.eval_count
    TokensPerSecond = $TokensPerSecond
}
