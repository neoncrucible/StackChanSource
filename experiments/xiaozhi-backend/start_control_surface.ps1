param()

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

if ($env:OS -ne "Windows_NT") {
    throw "Kadence Control Surface is currently a Windows-only Alpha 2 operator UI."
}

$UiScript = Join-Path $PSScriptRoot "control_surface\KadenceControlV3.ps1"
if (-not (Test-Path $UiScript)) {
    throw "Kadence Control Surface script not found: $UiScript"
}

$WindowsPowerShell = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
if (-not (Test-Path $WindowsPowerShell)) {
    throw "Windows PowerShell was not found: $WindowsPowerShell"
}

# Windows PowerShell 5.1 treats UTF-8 text without a BOM as the active ANSI
# code page. Execute a temporary UTF-8-with-BOM sibling copy so PSScriptRoot
# remains the real control_surface directory while parsing stays deterministic.
$TempUi = Join-Path (Split-Path $UiScript -Parent) ("KadenceControl-run-{0}.ps1" -f [guid]::NewGuid().ToString("N"))
$Utf8Bom = New-Object System.Text.UTF8Encoding($true)
$UiText = [System.IO.File]::ReadAllText($UiScript, [System.Text.Encoding]::UTF8)

# PowerShell automatic variables are case-insensitive, so a parameter named
# $Pid collides with the read-only built-in $PID. V3 used that name only in the
# port-conflict diagnostic helper. Patch the execution copy narrowly while the
# UI remains under active Alpha 2 iteration.
$UiText = $UiText.Replace('param([int]$Pid)', 'param([int]$ProcessId)')
$UiText = $UiText.Replace('("ProcessId={0}" -f $Pid)', '("ProcessId={0}" -f $ProcessId)')
$UiText = $UiText.Replace('("PID {0} / {1} / {2}" -f $Pid,$p.Name,$cmd)', '("PID {0} / {1} / {2}" -f $ProcessId,$p.Name,$cmd)')
$UiText = $UiText.Replace('("PID {0}" -f $Pid)', '("PID {0}" -f $ProcessId)')
$UiText = $UiText.Replace('(Describe-Process -Pid $c.Pid)', '(Describe-Process -ProcessId $c.Pid)')

# Milestone 3 keeps provider selection outside the UI, but the monitor must not
# lie about which provider is active. Make the runtime copy provider-neutral at
# rest and update the health tile when the Alpha 2 launcher announces its
# selected pre-boot profile.
$UiText = $UiText.Replace('Canonical identity / Gemini Flash-Lite', 'Canonical identity / Selected LLM')
$UiText = $UiText.Replace('@{Name="LLM";Value="Gemini 3.5 Flash-Lite"},', '@{Name="LLM";Value="Selected pre-boot"},')
$UiText = $UiText.Replace('$modelHealth = New-PanelLabel "MODEL  GEMINI"', '$modelHealth = New-PanelLabel "MODEL  WAITING"')

$LegacyModelBlock = @'
    if ($Line -match 'GeminiLLM') {
        $modelHealth.Text = "MODEL  GEMINI"; $modelHealth.ForeColor = $ColorCyan
    }
'@
$M3ModelBlock = @'
    if ($Line -match 'Kadence LLM profile: openai-luna') {
        $modelHealth.Text = "MODEL  GPT-5.6 LUNA"; $modelHealth.ForeColor = $ColorCyan
        $modeLabel.Text = "Canonical identity / GPT-5.6 Luna"
    }
    elseif ($Line -match 'Kadence LLM profile: gemini') {
        $modelHealth.Text = "MODEL  GEMINI"; $modelHealth.ForeColor = $ColorCyan
        $modeLabel.Text = "Canonical identity / Gemini Flash-Lite"
    }
    elseif ($Line -match 'GeminiLLM') {
        $modelHealth.Text = "MODEL  GEMINI"; $modelHealth.ForeColor = $ColorCyan
    }
'@
$UiText = $UiText.Replace($LegacyModelBlock.TrimEnd(), $M3ModelBlock.TrimEnd())

# When START SERVER is explicitly requested, reclaim only the exact stale
# Kadence backend signature (dedicated conda python + app.py owning BOTH 8000
# and 8003), then run the normal port preflight. Merely opening the UI never
# kills an existing process.
$UiText = $UiText.Replace(
    '$StartScript = Join-Path $BackendRoot "start_alpha2_windows.ps1"',
    '$StartScript = Join-Path $BackendRoot "start_alpha2_windows.ps1"' + [Environment]::NewLine + '$CleanupScript = Join-Path $BackendRoot "cleanup_stale_kadence_windows.ps1"'
)
$CleanupInjection = @'
    if (Test-Path $CleanupScript) {
        try {
            $cleaned = @(& $CleanupScript -PassThru)
            foreach ($item in $cleaned) {
                Append-Log ("[KADENCE UI] Reclaimed stale Kadence backend PID {0} (TCP {1})." -f $item.ProcessId,$item.Ports)
            }
        }
        catch {
            Append-Log ("[KADENCE UI] STALE CLEANUP WARNING: " + $_.Exception.Message)
        }
    }

    $conflicts = @(Get-PortConflicts)
'@
$UiText = $UiText.Replace('    $conflicts = @(Get-PortConflicts)', $CleanupInjection.TrimEnd())

[System.IO.File]::WriteAllText($TempUi, $UiText, $Utf8Bom)

Write-Host "Starting Kadence Control Surface..."
try {
    & $WindowsPowerShell -STA -NoLogo -NoProfile -ExecutionPolicy Bypass -File $TempUi
    $ExitCode = $LASTEXITCODE
}
finally {
    Remove-Item $TempUi -Force -ErrorAction SilentlyContinue
}

if ($ExitCode -ne 0) {
    throw "Kadence Control Surface exited with code $ExitCode. See the error above."
}

Write-Host "Kadence Control Surface closed."
