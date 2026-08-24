param()

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$script:KadenceExpectedPersonaSha256 = "7871c8453b3cf679c915c04220eef9bba14db535526d8e5bab666dbc66009aa1"
$script:KadenceLocalHost = "127.0.0.1:11434"
$script:KadenceLocalApiBase = "http://127.0.0.1:11434/api"

function Resolve-KadenceOllamaExe {
    $Candidates = New-Object System.Collections.Generic.List[string]

    $Command = Get-Command ollama.exe -ErrorAction SilentlyContinue
    if ($null -ne $Command -and -not [string]::IsNullOrWhiteSpace($Command.Source)) {
        $Candidates.Add($Command.Source)
    }

    foreach ($Candidate in @(
        (Join-Path $PSScriptRoot ".tools\ollama\ollama.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama.exe")
    )) {
        if (-not [string]::IsNullOrWhiteSpace($Candidate) -and -not $Candidates.Contains($Candidate)) {
            $Candidates.Add($Candidate)
        }
    }

    foreach ($Candidate in $Candidates) {
        if (Test-Path $Candidate) {
            return (Resolve-Path $Candidate).Path
        }
    }

    throw "Ollama was not found. Install Ollama for Windows, or place the standalone CLI at '$PSScriptRoot\.tools\ollama\ollama.exe'."
}

function Get-KadenceLocalPaths {
    param([Parameter(Mandatory = $true)][string]$RuntimeRoot)

    $Root = [System.IO.Path]::GetFullPath($RuntimeRoot)
    $StateDir = Join-Path $Root "ollama"
    return [pscustomobject]@{
        Root = $Root
        StateDir = $StateDir
        ModelsDir = (Join-Path $StateDir "models")
        PidPath = (Join-Path $StateDir "server.pid")
        StatePath = (Join-Path $StateDir "server.json")
        StdoutPath = (Join-Path $StateDir "server.stdout.log")
        StderrPath = (Join-Path $StateDir "server.stderr.log")
    }
}

function Get-KadencePortOwners {
    param([int]$Port = 11434)

    return @(
        Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue |
            Where-Object { $null -ne $_ } |
            Select-Object -ExpandProperty OwningProcess -Unique
    )
}

function Get-KadenceProcessInfo {
    param([Parameter(Mandatory = $true)][int]$ProcessId)

    return Get-CimInstance Win32_Process -Filter ("ProcessId={0}" -f $ProcessId) -ErrorAction SilentlyContinue
}

function Assert-KadenceOwnedOllamaProcess {
    param(
        [Parameter(Mandatory = $true)][int]$ProcessId,
        [Parameter(Mandatory = $true)][string]$ExpectedExecutable
    )

    $Info = Get-KadenceProcessInfo -ProcessId $ProcessId
    if ($null -eq $Info) {
        throw "Kadence LOCAL Ollama PID $ProcessId is not running."
    }

    $Name = [string]$Info.Name
    $ExecutablePath = [string]$Info.ExecutablePath
    $CommandLine = [string]$Info.CommandLine

    $ExpectedFull = [System.IO.Path]::GetFullPath($ExpectedExecutable)
    $ActualFull = if ([string]::IsNullOrWhiteSpace($ExecutablePath)) { "" } else { [System.IO.Path]::GetFullPath($ExecutablePath) }

    if ($Name -ine "ollama.exe" -or $ActualFull -ine $ExpectedFull -or $CommandLine -notmatch '(?i)(^|[\s"])serve(?:[\s"]|$)') {
        throw "PID $ProcessId does not match the Project-owned Ollama 'serve' signature. Refusing to control it."
    }

    return $Info
}

function Test-KadenceOllamaApi {
    try {
        $null = Invoke-RestMethod -Method Get -Uri "$script:KadenceLocalApiBase/version" -TimeoutSec 2
        return $true
    }
    catch {
        return $false
    }
}

function Invoke-KadenceOllamaApi {
    param(
        [Parameter(Mandatory = $true)][ValidateSet("Get","Post")][string]$Method,
        [Parameter(Mandatory = $true)][string]$Path,
        [object]$Body = $null,
        [int]$TimeoutSec = 300
    )

    $Uri = "$script:KadenceLocalApiBase/$Path"
    if ($Method -eq "Get") {
        return Invoke-RestMethod -Method Get -Uri $Uri -TimeoutSec $TimeoutSec
    }

    $Json = $Body | ConvertTo-Json -Depth 10 -Compress
    return Invoke-RestMethod -Method Post -Uri $Uri -ContentType "application/json" -Body $Json -TimeoutSec $TimeoutSec
}

function Get-KadenceCanonicalPersona {
    $PersonaPath = Join-Path $PSScriptRoot "persona\KADENCE_CANONICAL.md"
    if (-not (Test-Path $PersonaPath)) {
        throw "Canonical Kadence persona not found: $PersonaPath"
    }

    $ActualHash = (Get-FileHash -Path $PersonaPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($ActualHash -ne $script:KadenceExpectedPersonaSha256) {
        throw "Canonical persona SHA-256 mismatch. Expected $script:KadenceExpectedPersonaSha256, got $ActualHash. Refusing LOCAL inference."
    }

    $Text = [System.IO.File]::ReadAllText($PersonaPath, [System.Text.Encoding]::UTF8).Trim()
    if ([string]::IsNullOrWhiteSpace($Text)) {
        throw "Canonical Kadence persona is empty."
    }

    return [pscustomobject]@{
        Path = $PersonaPath
        Sha256 = $ActualHash
        Text = $Text
    }
}
