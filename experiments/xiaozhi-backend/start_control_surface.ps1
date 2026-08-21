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
# rest and update both the health tile and Active Stack after profile selection.
$UiText = $UiText.Replace('Canonical identity / Gemini Flash-Lite', 'Canonical identity / Selected LLM')
$UiText = $UiText.Replace('@{Name="LLM";Value="Gemini 3.5 Flash-Lite"},', '@{Name="LLM";Value="Selected pre-boot"},')
$UiText = $UiText.Replace('$modelHealth = New-PanelLabel "MODEL  GEMINI"', '$modelHealth = New-PanelLabel "MODEL  WAITING"')
$UiText = $UiText.Replace(
    '    $value.Font = New-Font 9' + [Environment]::NewLine + '    $left.Controls.Add($value)',
    '    $value.Font = New-Font 9' + [Environment]::NewLine + '    $value.AutoEllipsis = $true' + [Environment]::NewLine + '    if ($item.Name -eq "LLM") { $script:LlmStackValue = $value }' + [Environment]::NewLine + '    $left.Controls.Add($value)'
)

$LegacyModelBlock = @'
    if ($Line -match 'GeminiLLM') {
        $modelHealth.Text = "MODEL  GEMINI"; $modelHealth.ForeColor = $ColorCyan
    }
'@
$M3ModelBlock = @'
    if ($Line -match 'Kadence LLM profile: openai-luna') {
        $modelHealth.Text = "MODEL  GPT-5.6 LUNA"; $modelHealth.ForeColor = $ColorCyan
        $modeLabel.Text = "Canonical identity / GPT-5.6 Luna"
        if ($null -ne $script:LlmStackValue) { $script:LlmStackValue.Text = "GPT-5.6 Luna" }
    }
    elseif ($Line -match 'Kadence LLM profile: gemini') {
        $modelHealth.Text = "MODEL  GEMINI"; $modelHealth.ForeColor = $ColorCyan
        $modeLabel.Text = "Canonical identity / Gemini Flash-Lite"
        if ($null -ne $script:LlmStackValue) { $script:LlmStackValue.Text = "Gemini 3.5 Flash-Lite" }
    }
    elseif ($Line -match 'GeminiLLM') {
        $modelHealth.Text = "MODEL  GEMINI"; $modelHealth.ForeColor = $ColorCyan
    }
'@
$UiText = $UiText.Replace($LegacyModelBlock.TrimEnd(), $M3ModelBlock.TrimEnd())

# UI-only polish pass. These changes alter layout/readability only; backend,
# transport, endpointing, ASR, TTS and model behaviour are untouched.
$UiText = $UiText.Replace('$form.Size = New-Object System.Drawing.Size(1220,820)', '$form.Size = New-Object System.Drawing.Size(1320,840)')
$UiText = $UiText.Replace('$form.MinimumSize = New-Object System.Drawing.Size(1050,720)', '$form.MinimumSize = New-Object System.Drawing.Size(1100,720)')
$UiText = $UiText.Replace('$body.Padding = New-Object System.Windows.Forms.Padding(20,8,20,20)', '$body.Padding = New-Object System.Windows.Forms.Padding(22,8,22,22)')
$UiText = $UiText.Replace('Absolute,360', 'Absolute,340')
$UiText = $UiText.Replace('$left.Margin = New-Object System.Windows.Forms.Padding(0,0,12,0)', '$left.Margin = New-Object System.Windows.Forms.Padding(0,0,16,0)')
$UiText = $UiText.Replace('$buttonRow.Location = New-Object System.Drawing.Point(24,282)', '$buttonRow.Location = New-Object System.Drawing.Point(24,276)')
$UiText = $UiText.Replace('$divider.Location = New-Object System.Drawing.Point(24,354)', '$divider.Location = New-Object System.Drawing.Point(24,342)')
$UiText = $UiText.Replace('$stackTitle.Location = New-Object System.Drawing.Point(24,373)', '$stackTitle.Location = New-Object System.Drawing.Point(24,360)')
$UiText = $UiText.Replace('$y = 407', '$y = 392')
$UiText = $UiText.Replace('$healthGrid.Location = New-Object System.Drawing.Point(24,52)', '$healthGrid.Location = New-Object System.Drawing.Point(24,50)')
$UiText = $UiText.Replace('$healthGrid.Size = New-Object System.Drawing.Size(720,78)', '$healthGrid.Size = New-Object System.Drawing.Size(720,76)')
$UiText = $UiText.Replace('$lastTurnTitle.Location = New-Object System.Drawing.Point(24,154)', '$lastTurnTitle.Location = New-Object System.Drawing.Point(24,145)')
$UiText = $UiText.Replace('$lastTurn.Location = New-Object System.Drawing.Point(24,181)', '$lastTurn.Location = New-Object System.Drawing.Point(24,169)')
$UiText = $UiText.Replace('$lastTurn.Size = New-Object System.Drawing.Size(720,54)', '$lastTurn.Size = New-Object System.Drawing.Size(720,46)')
$UiText = $UiText.Replace('$logTitle.Location = New-Object System.Drawing.Point(24,260)', '$logTitle.Location = New-Object System.Drawing.Point(24,235)')
$UiText = $UiText.Replace('$clearButton.Location = New-Object System.Drawing.Point(666,251)', '$clearButton.Location = New-Object System.Drawing.Point(666,226)')
$UiText = $UiText.Replace('$logBox.Location = New-Object System.Drawing.Point(24,290)', '$logBox.Location = New-Object System.Drawing.Point(24,265)')
$UiText = $UiText.Replace('$logBox.Size = New-Object System.Drawing.Size(720,390)', '$logBox.Size = New-Object System.Drawing.Size(720,415)')
$UiText = $UiText.Replace('$logBox.Font = New-Font 8.5 ([System.Drawing.FontStyle]::Regular) "Consolas"', '$logBox.Font = New-Font 9 ([System.Drawing.FontStyle]::Regular) "Consolas"')

# Add a restrained divider under the product header to make the two dashboard
# panels read as one composed surface rather than two floating boxes.
$HeaderNeedle = '$header.Controls.Add($subtitle)'
$HeaderRule = @'
$header.Controls.Add($subtitle)

$headerRule = New-Object System.Windows.Forms.Label
$headerRule.Location = New-Object System.Drawing.Point(24,75)
$headerRule.Size = New-Object System.Drawing.Size(1160,1)
$headerRule.Anchor = "Top,Left,Right"
$headerRule.BackColor = $ColorBorder
$header.Controls.Add($headerRule)
'@
$UiText = $UiText.Replace($HeaderNeedle, $HeaderRule.TrimEnd())

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
