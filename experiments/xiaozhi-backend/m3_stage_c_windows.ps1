param(
    [ValidateSet("New", "A", "B", "Status", "Reveal", "Reset")]
    [string]$Action = "Status",
    [string]$RuntimeRoot = (Join-Path $PSScriptRoot ".runtime")
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$ProfileSetter = Join-Path $PSScriptRoot "set_llm_profile_windows.ps1"
$StageRoot = Join-Path $RuntimeRoot "benchmarks\m3-stage-c"
$ActiveSessionPath = Join-Path $StageRoot "active_session.json"
$ProfilePath = Join-Path $RuntimeRoot "kadence-llm-profile.txt"
$Utf8NoBom = [System.Text.UTF8Encoding]::new($false)

function Assert-ServerStopped {
    $Busy = New-Object System.Collections.Generic.List[string]

    foreach ($Entry in @(Get-NetUDPEndpoint -LocalPort 45872 -ErrorAction SilentlyContinue)) {
        if ($null -ne $Entry) {
            $Busy.Add("UDP 45872 (PID $($Entry.OwningProcess))")
        }
    }
    foreach ($Port in @(8000, 8003)) {
        foreach ($Entry in @(Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)) {
            if ($null -ne $Entry) {
                $Busy.Add("TCP $Port (PID $($Entry.OwningProcess))")
            }
        }
    }

    if ($Busy.Count -gt 0) {
        throw "Stop the Kadence server before changing a Stage C blind profile. Busy endpoint(s): $($Busy -join ', ')"
    }
}

function Read-JsonFile {
    param([Parameter(Mandatory = $true)][string]$Path)
    if (-not (Test-Path $Path)) {
        throw "Required Stage C file not found: $Path"
    }
    return ([System.IO.File]::ReadAllText($Path, [System.Text.Encoding]::UTF8) | ConvertFrom-Json)
}

function Write-JsonFile {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)]$Value
    )
    $Json = $Value | ConvertTo-Json -Depth 8
    [System.IO.File]::WriteAllText($Path, $Json + [Environment]::NewLine, $Utf8NoBom)
}

function Get-SavedProfile {
    if (-not (Test-Path $ProfilePath)) {
        return "gemini"
    }
    $Profile = ([System.IO.File]::ReadAllText($ProfilePath, [System.Text.Encoding]::UTF8)).Trim().ToLowerInvariant()
    if ($Profile -notin @("gemini", "luna")) {
        throw "Unsupported existing pre-boot profile '$Profile'."
    }
    return $Profile
}

function Set-UnderlyingProfile {
    param([Parameter(Mandatory = $true)][ValidateSet("gemini", "luna")][string]$Profile)
    if (-not (Test-Path $ProfileSetter)) {
        throw "LLM profile setter not found: $ProfileSetter"
    }
    & $ProfileSetter -Profile $Profile -RuntimeRoot $RuntimeRoot *> $null
}

function Get-ActiveSession {
    return (Read-JsonFile -Path $ActiveSessionPath)
}

function Get-BlindMapping {
    param([Parameter(Mandatory = $true)]$Session)
    return (Read-JsonFile -Path (Join-Path ([string]$Session.run_dir) "blind_mapping.json"))
}

function Arm-Label {
    param([Parameter(Mandatory = $true)][ValidateSet("A", "B")][string]$Label)

    Assert-ServerStopped
    $Session = Get-ActiveSession
    $Mapping = Get-BlindMapping -Session $Session
    $Provider = if ($Label -eq "A") { [string]$Mapping.A } else { [string]$Mapping.B }
    if ($Provider -notin @("gemini", "luna")) {
        throw "Invalid blind mapping for profile $Label."
    }

    Set-UnderlyingProfile -Profile $Provider
    $Session.active_label = $Label
    Write-JsonFile -Path $ActiveSessionPath -Value $Session

    Write-Host ""
    Write-Host "BLIND PROFILE $Label ARMED" -ForegroundColor Cyan
    Write-Host "Open the normal Kadence Control Surface and start the server."
    Write-Host "The model identity will be masked while this Stage C session is active."
    Write-Host "Do not open blind_mapping.json or the raw server log until your judgement is locked."
    Write-Host "Run folder: $($Session.run_dir)"
}

New-Item -ItemType Directory -Force -Path $StageRoot | Out-Null

switch ($Action) {
    "New" {
        Assert-ServerStopped
        if (Test-Path $ActiveSessionPath) {
            $Existing = Read-JsonFile -Path $ActiveSessionPath
            throw "A Stage C blind session is already active at '$($Existing.run_dir)'. Use -Action Reset before creating another."
        }

        $SavedProfile = Get-SavedProfile
        $RunId = Get-Date -Format "yyyyMMdd-HHmmss"
        $RunDir = Join-Path $StageRoot $RunId
        New-Item -ItemType Directory -Force -Path $RunDir | Out-Null

        $Byte = New-Object byte[] 1
        $Rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
        try {
            $Rng.GetBytes($Byte)
        }
        finally {
            $Rng.Dispose()
        }

        if (($Byte[0] % 2) -eq 0) {
            $Mapping = [ordered]@{ A = "gemini"; B = "luna" }
        }
        else {
            $Mapping = [ordered]@{ A = "luna"; B = "gemini" }
        }

        Write-JsonFile -Path (Join-Path $RunDir "blind_mapping.json") -Value $Mapping

        $Session = [ordered]@{
            run_id = $RunId
            run_dir = $RunDir
            active_label = "A"
            saved_profile = $SavedProfile
            created_utc = [DateTime]::UtcNow.ToString("o")
        }
        Write-JsonFile -Path $ActiveSessionPath -Value $Session

        $Review = @'
# Kadence M3 Stage C — Blind Physical Review

Use the exact same five prompts for A and B.

1. Who are you?
2. What is forty-six times nineteen? Reply with only the number.
3. Explain what a VPN does in one sentence.
4. My Windows PC says it is connected to Wi-Fi but has no internet. Give me the first two checks, concise.
5. I forgot to plug in the monitor and now the screen is black. Diagnose the problem.

Arithmetic target: 874.

Before revealing the mapping, record:

- Responsiveness: A / B / Tie
- Answer quality: A / B / Tie
- Kadence personality: A / B / Tie
- Spoken concision: A / B / Tie
- Instruction following: A / B / Tie
- Overall preference: A / B / Tie
- Any notes about pauses, awkwardness, verbosity, or standout answers.

Do not open blind_mapping.json, A-server.log, or B-server.log until the judgement is locked.
'@
        [System.IO.File]::WriteAllText((Join-Path $RunDir "review_sheet.md"), $Review.Trim() + [Environment]::NewLine, $Utf8NoBom)

        Set-UnderlyingProfile -Profile ([string]$Mapping.A)

        Write-Host "=== Kadence M3 Stage C / Blind Physical A-B ===" -ForegroundColor Cyan
        Write-Host "Blind session created. Profile A is armed."
        Write-Host "Run folder: $RunDir"
        Write-Host ""
        Write-Host "Open the normal Kadence Control Surface, power the robot, start the server, and speak prompts 1-5."
        Write-Host "When A is finished: STOP SERVER, close the Control Surface, then run:"
        Write-Host "  .\m3_stage_c_windows.ps1 -Action B" -ForegroundColor Yellow
        Write-Host ""
        Write-Host "Do not open blind_mapping.json or either raw server log yet."
    }

    "A" { Arm-Label -Label "A" }
    "B" { Arm-Label -Label "B" }

    "Status" {
        if (-not (Test-Path $ActiveSessionPath)) {
            Write-Host "No active M3 Stage C blind session."
            Write-Host "Create one with: .\m3_stage_c_windows.ps1 -Action New"
            break
        }
        $Session = Get-ActiveSession
        Write-Host "M3 Stage C blind session active." -ForegroundColor Cyan
        Write-Host "Run: $($Session.run_id)"
        Write-Host "Armed profile: $($Session.active_label)"
        Write-Host "Run folder: $($Session.run_dir)"
        Write-Host "Provider identity remains hidden."
    }

    "Reveal" {
        $Session = Get-ActiveSession
        $Mapping = Get-BlindMapping -Session $Session
        Write-Host "M3 Stage C mapping reveal:" -ForegroundColor Yellow
        Write-Host "A = $($Mapping.A)"
        Write-Host "B = $($Mapping.B)"
        Write-Host "Only reveal after the human A/B judgement has been locked."
    }

    "Reset" {
        Assert-ServerStopped
        $Session = Get-ActiveSession
        $SavedProfile = ([string]$Session.saved_profile).Trim().ToLowerInvariant()
        if ($SavedProfile -notin @("gemini", "luna")) {
            throw "Saved pre-Stage-C profile is invalid: '$SavedProfile'."
        }
        Set-UnderlyingProfile -Profile $SavedProfile
        Remove-Item $ActiveSessionPath -Force
        Write-Host "M3 Stage C blind UI mode cleared."
        Write-Host "Restored saved pre-boot profile: $SavedProfile"
        Write-Host "Stage C evidence retained at: $($Session.run_dir)"
    }
}
