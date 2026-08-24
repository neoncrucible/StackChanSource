param(
    [string]$RuntimeRoot = (Join-Path $PSScriptRoot ".runtime\local"),
    [string]$Model = "qwen3.5:4b",
    [bool]$PullIfMissing = $true,
    [int]$ContextLength = 8192
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

if ($env:OS -ne "Windows_NT") {
    throw "Kadence LOCAL runtime is currently Windows-only."
}

. (Join-Path $PSScriptRoot "kadence_local_common.ps1")

$Paths = Get-KadenceLocalPaths -RuntimeRoot $RuntimeRoot
$OllamaExe = Resolve-KadenceOllamaExe
$Persona = Get-KadenceCanonicalPersona

New-Item -ItemType Directory -Force -Path $Paths.StateDir, $Paths.ModelsDir | Out-Null

if (Test-Path $Paths.PidPath) {
    $ExistingText = [System.IO.File]::ReadAllText($Paths.PidPath).Trim()
    $ExistingPid = 0
    if ([int]::TryParse($ExistingText, [ref]$ExistingPid)) {
        $Existing = Get-KadenceProcessInfo -ProcessId $ExistingPid
        if ($null -ne $Existing) {
            throw "Kadence LOCAL runtime is already recorded as running at PID $ExistingPid. Stop it deliberately before starting another instance."
        }
    }
    Remove-Item $Paths.PidPath -Force -ErrorAction SilentlyContinue
    Remove-Item $Paths.StatePath -Force -ErrorAction SilentlyContinue
}

$PortOwners = @(Get-KadencePortOwners -Port 11434)
if ($PortOwners.Count -gt 0) {
    $Details = foreach ($Owner in $PortOwners) {
        $Info = Get-KadenceProcessInfo -ProcessId $Owner
        if ($null -eq $Info) { "PID $Owner" } else { "PID $Owner / $($Info.Name) / $($Info.CommandLine)" }
    }
    throw "TCP 11434 is already in use. Kadence will not hijack an existing Ollama or other service.`r`n$($Details -join "`r`n")"
}

$OldEnvironment = @{
    OLLAMA_HOST = $env:OLLAMA_HOST
    OLLAMA_MODELS = $env:OLLAMA_MODELS
    OLLAMA_NO_CLOUD = $env:OLLAMA_NO_CLOUD
    OLLAMA_KEEP_ALIVE = $env:OLLAMA_KEEP_ALIVE
    OLLAMA_MAX_LOADED_MODELS = $env:OLLAMA_MAX_LOADED_MODELS
    OLLAMA_NUM_PARALLEL = $env:OLLAMA_NUM_PARALLEL
    OLLAMA_CONTEXT_LENGTH = $env:OLLAMA_CONTEXT_LENGTH
}

$Process = $null
try {
    $env:OLLAMA_HOST = $script:KadenceLocalHost
    $env:OLLAMA_MODELS = $Paths.ModelsDir
    $env:OLLAMA_NO_CLOUD = "1"
    $env:OLLAMA_KEEP_ALIVE = "-1"
    $env:OLLAMA_MAX_LOADED_MODELS = "1"
    $env:OLLAMA_NUM_PARALLEL = "1"
    $env:OLLAMA_CONTEXT_LENGTH = [string]$ContextLength

    Remove-Item $Paths.StdoutPath, $Paths.StderrPath -Force -ErrorAction SilentlyContinue

    Write-Host "=== Kadence 2.0 Alpha 3 / LOCAL ==="
    Write-Host "Runtime: Ollama / Project-owned process"
    Write-Host "API: http://$script:KadenceLocalHost"
    Write-Host "Model store: $($Paths.ModelsDir)"
    Write-Host "Candidate model: $Model"
    Write-Host "Canonical identity: $($Persona.Sha256)"
    Write-Host ""

    $Process = Start-Process -FilePath $OllamaExe -ArgumentList "serve" -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput $Paths.StdoutPath -RedirectStandardError $Paths.StderrPath

    [System.IO.File]::WriteAllText($Paths.PidPath, [string]$Process.Id, [System.Text.UTF8Encoding]::new($false))

    $Ready = $false
    for ($Attempt = 0; $Attempt -lt 80; $Attempt++) {
        if ($Process.HasExited) {
            throw "Ollama server exited during startup with code $($Process.ExitCode). See $($Paths.StderrPath)"
        }
        if (Test-KadenceOllamaApi) {
            $Ready = $true
            break
        }
        Start-Sleep -Milliseconds 250
    }
    if (-not $Ready) {
        throw "Ollama API did not become ready on $script:KadenceLocalHost within 20 seconds."
    }

    $Tags = Invoke-KadenceOllamaApi -Method Get -Path "tags" -TimeoutSec 10
    $InstalledNames = @($Tags.models | ForEach-Object { [string]$_.name })
    $ModelPresent = $InstalledNames -contains $Model

    if (-not $ModelPresent) {
        if (-not $PullIfMissing) {
            throw "LOCAL model '$Model' is not installed in the Project-owned model store."
        }

        Write-Host "Pulling LOCAL candidate '$Model'..."
        & $OllamaExe pull $Model
        if ($LASTEXITCODE -ne 0) {
            throw "Ollama failed to pull '$Model' (exit code $LASTEXITCODE)."
        }
    }
    else {
        Write-Host "LOCAL model already present: $Model"
    }

    Write-Host "Preloading LOCAL model..."
    $PreloadBody = [ordered]@{
        model = $Model
        prompt = ""
        stream = $false
        keep_alive = -1
        options = [ordered]@{
            num_ctx = $ContextLength
        }
    }
    $null = Invoke-KadenceOllamaApi -Method Post -Path "generate" -Body $PreloadBody -TimeoutSec 300

    $State = [ordered]@{
        schema = "kadence.local-runtime.v1"
        engine = "LOCAL"
        provider = "ollama"
        model = $Model
        host = $script:KadenceLocalHost
        context_length = $ContextLength
        pid = $Process.Id
        executable = $OllamaExe
        model_store = $Paths.ModelsDir
        canonical_persona_sha256 = $Persona.Sha256
        started_utc = [DateTime]::UtcNow.ToString("o")
    }
    [System.IO.File]::WriteAllText(
        $Paths.StatePath,
        ($State | ConvertTo-Json -Depth 5),
        [System.Text.UTF8Encoding]::new($false)
    )

    Write-Host ""
    Write-Host "Kadence LOCAL runtime ready."
    Write-Host "PID: $($Process.Id)"
    & $OllamaExe ps
}
catch {
    if ($null -ne $Process -and -not $Process.HasExited) {
        & taskkill.exe /PID $Process.Id /T /F *> $null
    }
    Remove-Item $Paths.PidPath, $Paths.StatePath -Force -ErrorAction SilentlyContinue
    throw
}
finally {
    $env:OLLAMA_HOST = $OldEnvironment.OLLAMA_HOST
    $env:OLLAMA_MODELS = $OldEnvironment.OLLAMA_MODELS
    $env:OLLAMA_NO_CLOUD = $OldEnvironment.OLLAMA_NO_CLOUD
    $env:OLLAMA_KEEP_ALIVE = $OldEnvironment.OLLAMA_KEEP_ALIVE
    $env:OLLAMA_MAX_LOADED_MODELS = $OldEnvironment.OLLAMA_MAX_LOADED_MODELS
    $env:OLLAMA_NUM_PARALLEL = $OldEnvironment.OLLAMA_NUM_PARALLEL
    $env:OLLAMA_CONTEXT_LENGTH = $OldEnvironment.OLLAMA_CONTEXT_LENGTH
}
