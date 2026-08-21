param(
    [Parameter(Mandatory = $true)][string]$UiText
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

# Runtime patch for the frozen V3 WinForms source. This keeps the proven
# process-control/backend behaviour intact while allowing Alpha 2 UI iteration
# without touching voice transport or robot firmware.

# Fix the V3 diagnostic helper's collision with PowerShell's read-only $PID.
$UiText = $UiText.Replace('param([int]$Pid)', 'param([int]$ProcessId)')
$UiText = $UiText.Replace('("ProcessId={0}" -f $Pid)', '("ProcessId={0}" -f $ProcessId)')
$UiText = $UiText.Replace('("PID {0} / {1} / {2}" -f $Pid,$p.Name,$cmd)', '("PID {0} / {1} / {2}" -f $ProcessId,$p.Name,$cmd)')
$UiText = $UiText.Replace('("PID {0}" -f $Pid)', '("PID {0}" -f $ProcessId)')
$UiText = $UiText.Replace('(Describe-Process -Pid $c.Pid)', '(Describe-Process -ProcessId $c.Pid)')

# Provider-neutral idle state plus live profile reporting.
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

# --- V4 visual language -----------------------------------------------------
# This is intentionally a visible redesign rather than another spacing nudge.
$UiText = $UiText.Replace('$form.Size = New-Object System.Drawing.Size(1220,820)', '$form.Size = New-Object System.Drawing.Size(1360,860)')
$UiText = $UiText.Replace('$form.MinimumSize = New-Object System.Drawing.Size(1050,720)', '$form.MinimumSize = New-Object System.Drawing.Size(1180,740)')
$UiText = $UiText.Replace('Absolute,78', 'Absolute,96')
$UiText = $UiText.Replace('$title.Font = New-Font 19 ([System.Drawing.FontStyle]::Bold)', '$title.Font = New-Font 22 ([System.Drawing.FontStyle]::Bold)')
$UiText = $UiText.Replace('$title.Location = New-Object System.Drawing.Point(24,14)', '$title.Location = New-Object System.Drawing.Point(26,17)')
$UiText = $UiText.Replace('$subtitle.Location = New-Object System.Drawing.Point(27,49)', '$subtitle.Location = New-Object System.Drawing.Point(29,58)')
$UiText = $UiText.Replace('$body.Padding = New-Object System.Windows.Forms.Padding(20,8,20,20)', '$body.Padding = New-Object System.Windows.Forms.Padding(24,12,24,24)')
$UiText = $UiText.Replace('Absolute,360', 'Absolute,330')
$UiText = $UiText.Replace('$left.Margin = New-Object System.Windows.Forms.Padding(0,0,12,0)', '$left.Margin = New-Object System.Windows.Forms.Padding(0,0,18,0)')

# Make the two major surfaces read as deliberate dashboard cards.
$UiText = $UiText.Replace('$left.BackColor = $ColorPanel' + [Environment]::NewLine + '$left.Margin', '$left.BackColor = $ColorPanel' + [Environment]::NewLine + '$left.BorderStyle = "FixedSingle"' + [Environment]::NewLine + '$left.Margin')
$UiText = $UiText.Replace('$right.BackColor = $ColorPanel' + [Environment]::NewLine + '$right.Margin', '$right.BackColor = $ColorPanel' + [Environment]::NewLine + '$right.BorderStyle = "FixedSingle"' + [Environment]::NewLine + '$right.Margin')

# Left rail geometry.
$UiText = $UiText.Replace('$eyePanel.Location = New-Object System.Drawing.Point(24,18)', '$eyePanel.Location = New-Object System.Drawing.Point(23,20)')
$UiText = $UiText.Replace('$eyePanel.Size = New-Object System.Drawing.Size(312,178)', '$eyePanel.Size = New-Object System.Drawing.Size(280,190)')
$UiText = $UiText.Replace('$stateLabel.Size = New-Object System.Drawing.Size(312,34)', '$stateLabel.Size = New-Object System.Drawing.Size(280,38)')
$UiText = $UiText.Replace('$stateLabel.Location = New-Object System.Drawing.Point(24,204)', '$stateLabel.Location = New-Object System.Drawing.Point(23,220)')
$UiText = $UiText.Replace('$stateLabel.Font = New-Font 15 ([System.Drawing.FontStyle]::Bold)', '$stateLabel.Font = New-Font 17 ([System.Drawing.FontStyle]::Bold)')
$UiText = $UiText.Replace('$modeLabel.Size = New-Object System.Drawing.Size(312,24)', '$modeLabel.Size = New-Object System.Drawing.Size(280,24)')
$UiText = $UiText.Replace('$modeLabel.Location = New-Object System.Drawing.Point(24,238)', '$modeLabel.Location = New-Object System.Drawing.Point(23,258)')
$UiText = $UiText.Replace('$buttonRow.Location = New-Object System.Drawing.Point(24,282)', '$buttonRow.Location = New-Object System.Drawing.Point(23,298)')
$UiText = $UiText.Replace('$buttonRow.Size = New-Object System.Drawing.Size(312,46)', '$buttonRow.Size = New-Object System.Drawing.Size(280,50)')
$UiText = $UiText.Replace('$divider.Location = New-Object System.Drawing.Point(24,354)', '$divider.Location = New-Object System.Drawing.Point(23,372)')
$UiText = $UiText.Replace('$divider.Size = New-Object System.Drawing.Size(312,1)', '$divider.Size = New-Object System.Drawing.Size(280,1)')
$UiText = $UiText.Replace('$stackTitle.Location = New-Object System.Drawing.Point(24,373)', '$stackTitle.Location = New-Object System.Drawing.Point(23,392)')
$UiText = $UiText.Replace('$y = 407', '$y = 426')
$UiText = $UiText.Replace('$name.Location = New-Object System.Drawing.Point(24,$y)', '$name.Location = New-Object System.Drawing.Point(23,$y)')
$UiText = $UiText.Replace('$name.Size = New-Object System.Drawing.Size(92,22)', '$name.Size = New-Object System.Drawing.Size(86,22)')
$UiText = $UiText.Replace('$value.Location = New-Object System.Drawing.Point(118,$y)', '$value.Location = New-Object System.Drawing.Point(112,$y)')
$UiText = $UiText.Replace('$value.Size = New-Object System.Drawing.Size(218,22)', '$value.Size = New-Object System.Drawing.Size(190,22)')
$UiText = $UiText.Replace('$y += 31', '$y += 34')

# Health cards: larger, left-aligned, bordered and easier to scan.
$UiText = $UiText.Replace('$label.TextAlign = "MiddleCenter"', '$label.TextAlign = "MiddleLeft"')
$UiText = $UiText.Replace('$label.Font = New-Font 9 ([System.Drawing.FontStyle]::Bold)', '$label.Font = New-Font 8.5 ([System.Drawing.FontStyle]::Bold)' + [Environment]::NewLine + '    $label.Padding = New-Object System.Windows.Forms.Padding(12,0,8,0)' + [Environment]::NewLine + '    $label.BorderStyle = "FixedSingle"')
$UiText = $UiText.Replace('$healthTitle.Font = New-Font 10 ([System.Drawing.FontStyle]::Bold)', '$healthTitle.Font = New-Font 11 ([System.Drawing.FontStyle]::Bold)')
$UiText = $UiText.Replace('$healthGrid.Location = New-Object System.Drawing.Point(24,52)', '$healthGrid.Location = New-Object System.Drawing.Point(24,54)')
$UiText = $UiText.Replace('$healthGrid.Size = New-Object System.Drawing.Size(720,78)', '$healthGrid.Size = New-Object System.Drawing.Size(720,92)')

# Last heard becomes a proper transcript card.
$UiText = $UiText.Replace('$lastTurnTitle.Location = New-Object System.Drawing.Point(24,154)', '$lastTurnTitle.Location = New-Object System.Drawing.Point(24,170)')
$UiText = $UiText.Replace('$lastTurn.Location = New-Object System.Drawing.Point(24,181)', '$lastTurn.Location = New-Object System.Drawing.Point(24,198)')
$UiText = $UiText.Replace('$lastTurn.Size = New-Object System.Drawing.Size(720,54)', '$lastTurn.Size = New-Object System.Drawing.Size(720,58)')
$UiText = $UiText.Replace('$lastTurn.Font = New-Font 10', '$lastTurn.Font = New-Font 10' + [Environment]::NewLine + '$lastTurn.BorderStyle = "FixedSingle"')

# Give more room to the live log and remove the bright default RichTextBox frame.
$UiText = $UiText.Replace('$logTitle.Location = New-Object System.Drawing.Point(24,260)', '$logTitle.Location = New-Object System.Drawing.Point(24,282)')
$UiText = $UiText.Replace('$clearButton.Location = New-Object System.Drawing.Point(666,251)', '$clearButton.Location = New-Object System.Drawing.Point(666,270)')
$UiText = $UiText.Replace('$logBox.Location = New-Object System.Drawing.Point(24,290)', '$logBox.Location = New-Object System.Drawing.Point(24,314)')
$UiText = $UiText.Replace('$logBox.Size = New-Object System.Drawing.Size(720,390)', '$logBox.Size = New-Object System.Drawing.Size(720,390)')
$UiText = $UiText.Replace('$logBox.BorderStyle = "FixedSingle"', '$logBox.BorderStyle = "None"')
$UiText = $UiText.Replace('$logBox.Font = New-Font 8.5 ([System.Drawing.FontStyle]::Regular) "Consolas"', '$logBox.Font = New-Font 9 ([System.Drawing.FontStyle]::Regular) "Consolas"')

$LogFrameNeedle = '$right.Controls.Add($logBox)'
$LogFrameBlock = @'
$logFrame = New-Object System.Windows.Forms.Panel
$logFrame.Location = New-Object System.Drawing.Point(24,314)
$logFrame.Size = New-Object System.Drawing.Size(720,390)
$logFrame.Anchor = "Top,Bottom,Left,Right"
$logFrame.BackColor = $ColorBorder
$right.Controls.Add($logFrame)
$right.Controls.Remove($logBox)
$logBox.Location = New-Object System.Drawing.Point(1,1)
$logBox.Size = New-Object System.Drawing.Size(718,388)
$logBox.Anchor = "Top,Bottom,Left,Right"
$logFrame.Controls.Add($logBox)
'@
$UiText = $UiText.Replace($LogFrameNeedle, $LogFrameBlock.TrimEnd())
$UiText = $UiText.Replace('    $logBox.Width = $width', '    $logFrame.Width = $width')

# Stronger product header: milestone badge, local badge and cyan baseline.
$HeaderNeedle = '$header.Controls.Add($subtitle)'
$HeaderBlock = @'
$header.Controls.Add($subtitle)

$milestoneBadge = New-Object System.Windows.Forms.Label
$milestoneBadge.AutoSize = $false
$milestoneBadge.Size = New-Object System.Drawing.Size(178,28)
$milestoneBadge.Location = New-Object System.Drawing.Point(1015,22)
$milestoneBadge.Anchor = "Top,Right"
$milestoneBadge.Text = "ALPHA 2  //  MILESTONE 3"
$milestoneBadge.TextAlign = "MiddleCenter"
$milestoneBadge.BackColor = $ColorPanelAlt
$milestoneBadge.ForeColor = $ColorCyan
$milestoneBadge.BorderStyle = "FixedSingle"
$milestoneBadge.Font = New-Font 8 ([System.Drawing.FontStyle]::Bold)
$header.Controls.Add($milestoneBadge)

$localBadge = New-Object System.Windows.Forms.Label
$localBadge.AutoSize = $false
$localBadge.Size = New-Object System.Drawing.Size(72,28)
$localBadge.Location = New-Object System.Drawing.Point(1200,22)
$localBadge.Anchor = "Top,Right"
$localBadge.Text = "LOCAL"
$localBadge.TextAlign = "MiddleCenter"
$localBadge.BackColor = $ColorPanelAlt
$localBadge.ForeColor = $ColorTeal
$localBadge.BorderStyle = "FixedSingle"
$localBadge.Font = New-Font 8 ([System.Drawing.FontStyle]::Bold)
$header.Controls.Add($localBadge)

$headerRule = New-Object System.Windows.Forms.Label
$headerRule.Location = New-Object System.Drawing.Point(26,91)
$headerRule.Size = New-Object System.Drawing.Size(1260,2)
$headerRule.Anchor = "Top,Left,Right"
$headerRule.BackColor = $ColorCyan
$header.Controls.Add($headerRule)
'@
$UiText = $UiText.Replace($HeaderNeedle, $HeaderBlock.TrimEnd())

# Cyan rail on the operator card plus a small anchored footer identity.
$LeftNeedle = '$body.Controls.Add($left,0,0)'
$LeftBlock = @'
$body.Controls.Add($left,0,0)

$leftAccent = New-Object System.Windows.Forms.Panel
$leftAccent.Location = New-Object System.Drawing.Point(0,0)
$leftAccent.Size = New-Object System.Drawing.Size(3,720)
$leftAccent.Anchor = "Top,Bottom,Left"
$leftAccent.BackColor = $ColorCyan
$left.Controls.Add($leftAccent)

$leftFooter = New-Object System.Windows.Forms.Label
$leftFooter.AutoSize = $false
$leftFooter.Size = New-Object System.Drawing.Size(280,22)
$leftFooter.Location = New-Object System.Drawing.Point(23,655)
$leftFooter.Anchor = "Bottom,Left"
$leftFooter.Text = "LOCAL RUNTIME  //  PRE-BOOT PROFILE"
$leftFooter.TextAlign = "MiddleLeft"
$leftFooter.ForeColor = $ColorOffline
$leftFooter.Font = New-Font 7.5 ([System.Drawing.FontStyle]::Bold)
$left.Controls.Add($leftFooter)
'@
$UiText = $UiText.Replace($LeftNeedle, $LeftBlock.TrimEnd())

# Read the already-selected local profile before server start so the idle UI
# immediately reflects the real next-boot model rather than saying "waiting".
$ReadyNeedle = 'Append-Log "[KADENCE UI] Control Surface ready."'
$ReadyBlock = @'
$profilePath = Join-Path $BackendRoot ".runtime\kadence-llm-profile.txt"
if (Test-Path $profilePath) {
    try {
        $idleProfile = [System.IO.File]::ReadAllText($profilePath,[System.Text.Encoding]::UTF8).Trim().ToLowerInvariant()
        if ($idleProfile -eq "luna") {
            $modelHealth.Text = "MODEL  GPT-5.6 LUNA"; $modelHealth.ForeColor = $ColorCyan
            $modeLabel.Text = "Canonical identity / GPT-5.6 Luna"
            if ($null -ne $script:LlmStackValue) { $script:LlmStackValue.Text = "GPT-5.6 Luna" }
        }
        elseif ($idleProfile -eq "gemini") {
            $modelHealth.Text = "MODEL  GEMINI"; $modelHealth.ForeColor = $ColorCyan
            $modeLabel.Text = "Canonical identity / Gemini Flash-Lite"
            if ($null -ne $script:LlmStackValue) { $script:LlmStackValue.Text = "Gemini 3.5 Flash-Lite" }
        }
    }
    catch {}
}

Append-Log "[KADENCE UI] Control Surface V4 ready."
'@
$UiText = $UiText.Replace($ReadyNeedle, $ReadyBlock.TrimEnd())

# Keep the narrow stale-backend reclaim from the validated M2 launcher.
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

return $UiText
