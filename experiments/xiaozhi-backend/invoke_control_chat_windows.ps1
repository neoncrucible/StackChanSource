param(
    [Parameter(Mandatory = $true)][ValidateSet("LOCAL","LUNA")][string]$Engine,
    [Parameter(Mandatory = $true)][object[]]$Messages,
    [string]$LocalRuntimeRoot = (Join-Path $PSScriptRoot ".runtime\local"),
    [int]$MaxHistoryMessages = 16
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

if ($env:OS -ne "Windows_NT") {
    throw "Kadence Control Surface chat is currently Windows-only."
}

. (Join-Path $PSScriptRoot "kadence_local_common.ps1")

$Persona = Get-KadenceCanonicalPersona
$Normalized = New-Object System.Collections.Generic.List[object]

foreach ($Message in @($Messages)) {
    if ($null -eq $Message) { continue }

    $Role = [string]$Message.role
    $Content = [string]$Message.content

    if ($Role -notin @("user","assistant")) {
        throw "Control Surface chat history contains unsupported role '$Role'."
    }
    if ([string]::IsNullOrWhiteSpace($Content)) {
        continue
    }

    $Normalized.Add([ordered]@{
        role = $Role
        content = $Content.Trim()
    })
}

if ($Normalized.Count -eq 0) {
    throw "Control Surface chat requires at least one user message."
}

if ($MaxHistoryMessages -lt 2) {
    throw "MaxHistoryMessages must be at least 2."
}

# Windows PowerShell 5.1 can throw "Argument types do not match" when a
# Generic.List[object] is forced through @(...). Convert explicitly instead.
$History = $Normalized.ToArray()
if ($History.Count -gt $MaxHistoryMessages) {
    $History = @($History | Select-Object -Last $MaxHistoryMessages)
}

$Dialogue = New-Object System.Collections.Generic.List[object]
$Dialogue.Add([ordered]@{ role = "system"; content = $Persona.Text })
foreach ($Item in $History) {
    $Dialogue.Add($Item)
}

$Wall = [System.Diagnostics.Stopwatch]::StartNew()

if ($Engine -eq "LOCAL") {
    $Paths = Get-KadenceLocalPaths -RuntimeRoot $LocalRuntimeRoot
    if (-not (Test-Path $Paths.StatePath) -or -not (Test-Path $Paths.PidPath)) {
        throw "LOCAL is not running. Start the LOCAL engine from the Control Surface first."
    }

    $State = Get-Content $Paths.StatePath -Raw | ConvertFrom-Json
    $ProcessId = [int]$State.pid
    $null = Assert-KadenceOwnedOllamaProcess -ProcessId $ProcessId -ExpectedExecutable ([string]$State.executable)

    $Owners = @(Get-KadencePortOwners -Port 11434)
    if ($Owners -notcontains $ProcessId) {
        throw "LOCAL ownership verification failed: recorded PID $ProcessId does not own TCP 11434."
    }
    if (-not (Test-KadenceOllamaApi)) {
        throw "LOCAL Ollama API is not responding."
    }
    if ([string]$State.canonical_persona_sha256 -ne $Persona.Sha256) {
        throw "LOCAL identity state no longer matches the canonical Kadence persona. Restart LOCAL before chatting."
    }

    $Body = [ordered]@{
        model = [string]$State.model
        messages = $Dialogue.ToArray()
        stream = $false
        think = $false
        keep_alive = -1
        options = [ordered]@{
            num_ctx = [int]$State.context_length
            temperature = 0.6
            top_p = 0.9
            num_predict = 320
        }
    }

    $Response = Invoke-KadenceOllamaApi -Method Post -Path "chat" -Body $Body -TimeoutSec 300
    $Wall.Stop()

    $Text = [string]$Response.message.content
    if ([string]::IsNullOrWhiteSpace($Text)) {
        throw "LOCAL returned an empty Control Surface chat response."
    }

    return [pscustomobject]@{
        Engine = "LOCAL"
        Model = [string]$State.model
        Text = $Text.Trim()
        WallMilliseconds = [Math]::Round($Wall.Elapsed.TotalMilliseconds, 1)
    }
}

$RuntimeRoot = Join-Path $PSScriptRoot ".runtime"
$ConfigPath = Join-Path $RuntimeRoot "xiaozhi-esp32-server\main\xiaozhi-server\data\.config.yaml"
if (-not (Test-Path $ConfigPath)) {
    throw "LUNA runtime config was not found: $ConfigPath"
}

$LunaListener = @(Get-NetTCPConnection -State Listen -LocalPort 8000 -ErrorAction SilentlyContinue)
if ($LunaListener.Count -eq 0) {
    throw "LUNA backend is not listening on TCP 8000. Start LUNA from the Control Surface first."
}

$ConfigText = [System.IO.File]::ReadAllText($ConfigPath, [System.Text.Encoding]::UTF8)

$AsrBlock = [regex]::Match(
    $ConfigText,
    '(?ms)^  OpenaiRealtimeASR:\s*\r?\n(?<body>.*?)(?=^  \S|\z)'
)
if (-not $AsrBlock.Success) {
    throw "OpenaiRealtimeASR config block was not found; refusing to invent a LUNA credential source."
}

$KeyMatch = [regex]::Match($AsrBlock.Groups['body'].Value, '(?m)^    api_key:\s*(.+?)\s*$')
if (-not $KeyMatch.Success -or [string]::IsNullOrWhiteSpace($KeyMatch.Groups[1].Value)) {
    throw "OpenaiRealtimeASR api_key line was not found or was empty."
}

$ApiKey = $KeyMatch.Groups[1].Value.Trim().Trim('"').Trim("'")
if ([string]::IsNullOrWhiteSpace($ApiKey)) {
    throw "Resolved LUNA API key was empty."
}

$OpenAiBlock = [regex]::Match(
    $ConfigText,
    '(?ms)^  OpenAILLM:\s*\r?\n(?<body>.*?)(?=^  \S|^\S|\z)'
)
if (-not $OpenAiBlock.Success) {
    throw "Accepted OpenAILLM LUNA profile is not present. Start LUNA deliberately before chatting."
}
if ($OpenAiBlock.Groups['body'].Value -notmatch '(?m)^    model_name:\s*"?gpt-5\.6-luna"?\s*$') {
    throw "Configured OpenAILLM profile is not gpt-5.6-luna. Refusing to silently route elsewhere."
}
if ($OpenAiBlock.Groups['body'].Value -notmatch '(?m)^    reasoning_effort:\s*"?none"?\s*$') {
    throw "Configured LUNA profile does not use reasoning_effort=none. Refusing to alter the accepted profile."
}

$Body = [ordered]@{
    model = "gpt-5.6-luna"
    messages = $Dialogue.ToArray()
    stream = $false
    reasoning_effort = "none"
}

$Json = $Body | ConvertTo-Json -Depth 12 -Compress

# Windows PowerShell 5.1 can mojibake UTF-8 JSON returned without an explicit
# response charset (for example an em dash becoming "â€”"). Read the raw response
# bytes and decode them as UTF-8, which is the JSON wire encoding used here.
Add-Type -AssemblyName System.Net.Http
$HttpClient = New-Object System.Net.Http.HttpClient
$HttpClient.Timeout = [TimeSpan]::FromSeconds(300)
$HttpClient.DefaultRequestHeaders.Authorization = New-Object System.Net.Http.Headers.AuthenticationHeaderValue("Bearer", $ApiKey)
$HttpContent = New-Object System.Net.Http.StringContent($Json, [System.Text.Encoding]::UTF8, "application/json")
try {
    $HttpResponse = $HttpClient.PostAsync("https://api.openai.com/v1/chat/completions", $HttpContent).GetAwaiter().GetResult()
    $ResponseBytes = $HttpResponse.Content.ReadAsByteArrayAsync().GetAwaiter().GetResult()
    $ResponseText = [System.Text.Encoding]::UTF8.GetString($ResponseBytes)

    if (-not $HttpResponse.IsSuccessStatusCode) {
        throw ("LUNA chat request failed: HTTP {0} {1}" -f [int]$HttpResponse.StatusCode, $ResponseText)
    }

    $Response = $ResponseText | ConvertFrom-Json
}
finally {
    if ($null -ne $HttpContent) { $HttpContent.Dispose() }
    if ($null -ne $HttpClient) { $HttpClient.Dispose() }
}

$Wall.Stop()

$Text = [string]$Response.choices[0].message.content
if ([string]::IsNullOrWhiteSpace($Text)) {
    throw "LUNA returned an empty Control Surface chat response."
}

return [pscustomobject]@{
    Engine = "LUNA"
    Model = "gpt-5.6-luna"
    Text = $Text.Trim()
    WallMilliseconds = [Math]::Round($Wall.Elapsed.TotalMilliseconds, 1)
}
