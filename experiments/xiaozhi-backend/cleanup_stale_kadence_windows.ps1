param(
    [switch]$PassThru
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

# This helper deliberately kills only a very narrow stale-backend signature:
# one process must own BOTH Xiaozhi TCP listeners (8000 and 8003), be Python,
# run app.py, and come from the dedicated kadence2-xiaozhi Conda environment.
# Anything else is left untouched and will be reported by normal preflight.

$RequiredPorts = @(8000, 8003)
$Listeners = @()
foreach ($Port in $RequiredPorts) {
    $Listeners += @(Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)
}

$CandidateIds = @(
    $Listeners |
        Where-Object { $null -ne $_ } |
        Select-Object -ExpandProperty OwningProcess -Unique
)

foreach ($ProcessId in $CandidateIds) {
    $OwnedPorts = @(
        $Listeners |
            Where-Object { $_.OwningProcess -eq $ProcessId } |
            Select-Object -ExpandProperty LocalPort -Unique
    )

    if (($OwnedPorts -notcontains 8000) -or ($OwnedPorts -notcontains 8003)) {
        continue
    }

    $ProcessInfo = Get-CimInstance Win32_Process -Filter ("ProcessId={0}" -f $ProcessId) -ErrorAction SilentlyContinue
    if ($null -eq $ProcessInfo) {
        continue
    }

    $Name = [string]$ProcessInfo.Name
    $ExecutablePath = [string]$ProcessInfo.ExecutablePath
    $CommandLine = [string]$ProcessInfo.CommandLine

    $LooksLikeKadencePython =
        (($Name -ieq "python.exe") -or ($Name -ieq "pythonw.exe")) -and
        ($ExecutablePath -match '(?i)\\envs\\kadence2-xiaozhi\\python(?:w)?\.exe$') -and
        ($CommandLine -match '(?i)(^|[\s\"])(?:[^\"]*\\)?app\.py(?:[\s\"]|$)')

    if (-not $LooksLikeKadencePython) {
        continue
    }

    if (-not $PassThru) {
        Write-Host "Stopping stale Kadence backend PID $ProcessId (TCP 8000/8003)..."
    }

    & taskkill.exe /PID $ProcessId /T /F *> $null
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to stop stale Kadence backend PID $ProcessId (taskkill exit code $LASTEXITCODE)."
    }

    Start-Sleep -Milliseconds 350

    if ($PassThru) {
        [pscustomobject]@{
            ProcessId = $ProcessId
            Name = $Name
            Ports = "8000,8003"
        }
    }
}
