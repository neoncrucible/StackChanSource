param(
    [Parameter(Mandatory = $true)][string]$UiText
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

# Alpha 3 overlay only. The accepted V3 -> V4 -> V4.1 -> V4.3 -> EYE chain
# remains untouched. This patch adds explicit LOCAL/LUNA selection and a
# Control-Surface-owned text chat window. There is no AUTO mode and no fallback.

function Replace-Required {
    param(
        [Parameter(Mandatory = $true)][string]$Text,
        [Parameter(Mandatory = $true)][string]$From,
        [Parameter(Mandatory = $true)][string]$To,
        [Parameter(Mandatory = $true)][string]$Label
    )

    if (-not $Text.Contains($From)) {
        throw "Alpha 3 Control Surface patch guard failed: $Label"
    }
    return $Text.Replace($From, $To)
}

$Nl = [Environment]::NewLine
$Working = $UiText

# --- Alpha 3 dependencies / state ------------------------------------------
$Working = Replace-Required -Text $Working `
    -From '$CleanupScript = Join-Path $BackendRoot "cleanup_stale_kadence_windows.ps1"' `
    -To ('$CleanupScript = Join-Path $BackendRoot "cleanup_stale_kadence_windows.ps1"' + $Nl +
         '$LocalStartScript = Join-Path $BackendRoot "start_local_windows.ps1"' + $Nl +
         '$LocalStopScript = Join-Path $BackendRoot "stop_local_windows.ps1"' + $Nl +
         '$ControlChatScript = Join-Path $BackendRoot "invoke_control_chat_windows.ps1"') `
    -Label 'Alpha 3 dependency insertion anchor'

$OldDependencyGuard = @'
if (-not (Test-Path $StartScript)) {
    [System.Windows.Forms.MessageBox]::Show("Alpha 2 launcher not found:`r`n$StartScript", "Kadence Control Surface") | Out-Null
    exit 1
}
'@
$NewDependencyGuard = @'
foreach ($RequiredAlpha3Path in @($StartScript,$LocalStartScript,$LocalStopScript,$ControlChatScript)) {
    if (-not (Test-Path $RequiredAlpha3Path)) {
        [System.Windows.Forms.MessageBox]::Show("Alpha 3 Control Surface dependency not found:`r`n$RequiredAlpha3Path", "Kadence Control Surface") | Out-Null
        exit 1
    }
}
'@
$Working = Replace-Required -Text $Working -From $OldDependencyGuard.TrimEnd() -To $NewDependencyGuard.TrimEnd() -Label 'dependency guard'

$Working = Replace-Required -Text $Working `
    -From '$script:EyeState = "offline"' `
    -To ('$script:EyeState = "offline"' + $Nl +
         '$script:SelectedEngine = "LOCAL"' + $Nl +
         '$script:LocalRunning = $false' + $Nl +
         '$script:ChatMessages = New-Object System.Collections.Generic.List[object]' + $Nl +
         '$script:ChatForm = $null') `
    -Label 'Alpha 3 state insertion'

# --- Header / engine selection ---------------------------------------------
$Working = Replace-Required -Text $Working -From '$milestoneBadge.Text = "ALPHA 2"' -To '$milestoneBadge.Text = "ALPHA 3"' -Label 'Alpha 3 phase badge'

$EngineUiAnchor = '$left.Controls.Add($modeLabel)'
$EngineUiBlock = @'
$left.Controls.Add($modeLabel)

$engineRow = New-Object System.Windows.Forms.Panel
$engineRow.Location = New-Object System.Drawing.Point(23,289)
$engineRow.Size = New-Object System.Drawing.Size(280,34)
$engineRow.BackColor = $ColorPanel
$left.Controls.Add($engineRow)

$engineTitle = New-Object System.Windows.Forms.Label
$engineTitle.Location = New-Object System.Drawing.Point(0,7)
$engineTitle.Size = New-Object System.Drawing.Size(62,22)
$engineTitle.Text = "ENGINE"
$engineTitle.ForeColor = $ColorMuted
$engineTitle.Font = New-Font 8 ([System.Drawing.FontStyle]::Bold)
$engineRow.Controls.Add($engineTitle)

$localEngineButton = New-Object System.Windows.Forms.RadioButton
$localEngineButton.Appearance = "Button"
$localEngineButton.FlatStyle = "Flat"
$localEngineButton.FlatAppearance.BorderSize = 1
$localEngineButton.FlatAppearance.BorderColor = $ColorCyan
$localEngineButton.Size = New-Object System.Drawing.Size(96,30)
$localEngineButton.Location = New-Object System.Drawing.Point(72,2)
$localEngineButton.Text = "LOCAL"
$localEngineButton.TextAlign = "MiddleCenter"
$localEngineButton.BackColor = $ColorPanelAlt
$localEngineButton.ForeColor = $ColorCyan
$localEngineButton.Font = New-Font 8.5 ([System.Drawing.FontStyle]::Bold)
$engineRow.Controls.Add($localEngineButton)

$lunaEngineButton = New-Object System.Windows.Forms.RadioButton
$lunaEngineButton.Appearance = "Button"
$lunaEngineButton.FlatStyle = "Flat"
$lunaEngineButton.FlatAppearance.BorderSize = 1
$lunaEngineButton.FlatAppearance.BorderColor = $ColorBorder
$lunaEngineButton.Size = New-Object System.Drawing.Size(96,30)
$lunaEngineButton.Location = New-Object System.Drawing.Point(178,2)
$lunaEngineButton.Text = "LUNA"
$lunaEngineButton.TextAlign = "MiddleCenter"
$lunaEngineButton.BackColor = $ColorPanelAlt
$lunaEngineButton.ForeColor = $ColorMuted
$lunaEngineButton.Font = New-Font 8.5 ([System.Drawing.FontStyle]::Bold)
$engineRow.Controls.Add($lunaEngineButton)
'@
$Working = Replace-Required -Text $Working -From $EngineUiAnchor -To $EngineUiBlock.TrimEnd() -Label 'engine selector UI'

$Working = Replace-Required -Text $Working -From '$buttonRow.Location = New-Object System.Drawing.Point(23,298)' -To '$buttonRow.Location = New-Object System.Drawing.Point(23,334)' -Label 'button row geometry'
$Working = Replace-Required -Text $Working -From '$divider.Location = New-Object System.Drawing.Point(23,372)' -To '$divider.Location = New-Object System.Drawing.Point(23,402)' -Label 'divider geometry'
$Working = Replace-Required -Text $Working -From '$stackTitle.Location = New-Object System.Drawing.Point(23,392)' -To '$stackTitle.Location = New-Object System.Drawing.Point(23,422)' -Label 'stack title geometry'
$Working = Replace-Required -Text $Working -From '$y = 426' -To '$y = 456' -Label 'stack value geometry'

$OldColumns = @'
$buttonRow.ColumnCount = 2
$buttonRow.RowCount = 1
$buttonRow.ColumnStyles.Add((New-Object System.Windows.Forms.ColumnStyle([System.Windows.Forms.SizeType]::Percent,50))) | Out-Null
$buttonRow.ColumnStyles.Add((New-Object System.Windows.Forms.ColumnStyle([System.Windows.Forms.SizeType]::Percent,50))) | Out-Null
'@
$NewColumns = @'
$buttonRow.ColumnCount = 3
$buttonRow.RowCount = 1
$buttonRow.ColumnStyles.Add((New-Object System.Windows.Forms.ColumnStyle([System.Windows.Forms.SizeType]::Percent,33.333))) | Out-Null
$buttonRow.ColumnStyles.Add((New-Object System.Windows.Forms.ColumnStyle([System.Windows.Forms.SizeType]::Percent,33.333))) | Out-Null
$buttonRow.ColumnStyles.Add((New-Object System.Windows.Forms.ColumnStyle([System.Windows.Forms.SizeType]::Percent,33.334))) | Out-Null
'@
$Working = Replace-Required -Text $Working -From $OldColumns.TrimEnd() -To $NewColumns.TrimEnd() -Label 'three-way operator button row'
$Working = Replace-Required -Text $Working -From '$startButton.Text = "START SERVER"' -To '$startButton.Text = "START"' -Label 'START button label'
$Working = Replace-Required -Text $Working -From '$stopButton.Text = "STOP SERVER"' -To '$stopButton.Text = "STOP"' -Label 'STOP button label'
$Working = Replace-Required -Text $Working -From '$startButton.Margin = New-Object System.Windows.Forms.Padding(0,0,6,0)' -To '$startButton.Margin = New-Object System.Windows.Forms.Padding(0,0,4,0)' -Label 'START button spacing'
$Working = Replace-Required -Text $Working -From '$stopButton.Margin = New-Object System.Windows.Forms.Padding(6,0,0,0)' -To '$stopButton.Margin = New-Object System.Windows.Forms.Padding(4,0,4,0)' -Label 'STOP button spacing'

$ChatButtonAnchor = '$buttonRow.Controls.Add($stopButton,1,0)'
$ChatButtonBlock = @'
$buttonRow.Controls.Add($stopButton,1,0)

$chatButton = New-Object System.Windows.Forms.Button
$chatButton.Text = "CHAT"
$chatButton.Dock = "Fill"
$chatButton.Margin = New-Object System.Windows.Forms.Padding(4,0,0,0)
$chatButton.FlatStyle = "Flat"
$chatButton.FlatAppearance.BorderColor = $ColorOffline
$chatButton.FlatAppearance.BorderSize = 1
$chatButton.BackColor = $ColorPanelAlt
$chatButton.ForeColor = $ColorOffline
$chatButton.Font = New-Font 9 ([System.Drawing.FontStyle]::Bold)
$chatButton.Enabled = $false
$buttonRow.Controls.Add($chatButton,2,0)
'@
$Working = Replace-Required -Text $Working -From $ChatButtonAnchor -To $ChatButtonBlock.TrimEnd() -Label 'CHAT button'

# --- Engine identity / chat functions --------------------------------------
$SetEyeNeedle = @'
function Set-EyeState {
    param([string]$State)
    $script:EyeState = $State
    $eyePanel.Invalidate()
}
'@
$Alpha3Functions = @'
function Set-EyeState {
    param([string]$State)
    $script:EyeState = $State
    $eyePanel.Invalidate()
}

function Set-EngineSelectionEnabled {
    param([bool]$Enabled)
    $localEngineButton.Enabled = $Enabled
    $lunaEngineButton.Enabled = $Enabled
}

function Update-SelectedEngineDisplay {
    if ($script:SelectedEngine -eq "LOCAL") {
        $localEngineButton.Checked = $true
        $lunaEngineButton.Checked = $false
        $localEngineButton.ForeColor = $ColorCyan
        $localEngineButton.FlatAppearance.BorderColor = $ColorCyan
        $lunaEngineButton.ForeColor = $ColorMuted
        $lunaEngineButton.FlatAppearance.BorderColor = $ColorBorder
        $localBadge.Text = "LOCAL"
        $localBadge.ForeColor = $ColorTeal
        $modeLabel.Text = "Canonical identity / qwen3.5:4b"
        $modelHealth.Text = "MODEL  QWEN3.5 4B"; $modelHealth.ForeColor = $ColorCyan
        $transportHealth.Text = "TRANSPORT  DEFERRED"; $transportHealth.ForeColor = $ColorOffline
        if ($null -ne $script:LlmStackValue) { $script:LlmStackValue.Text = "qwen3.5:4b / LOCAL" }
    }
    else {
        $localEngineButton.Checked = $false
        $lunaEngineButton.Checked = $true
        $localEngineButton.ForeColor = $ColorMuted
        $localEngineButton.FlatAppearance.BorderColor = $ColorBorder
        $lunaEngineButton.ForeColor = $ColorCyan
        $lunaEngineButton.FlatAppearance.BorderColor = $ColorCyan
        $localBadge.Text = "LUNA"
        $localBadge.ForeColor = $ColorCyan
        $modeLabel.Text = "Canonical identity / GPT-5.6 Luna"
        $modelHealth.Text = "MODEL  GPT-5.6 LUNA"; $modelHealth.ForeColor = $ColorCyan
        $transportHealth.Text = "TRANSPORT  FROZEN"; $transportHealth.ForeColor = $ColorCyan
        if ($null -ne $script:LlmStackValue) { $script:LlmStackValue.Text = "GPT-5.6 Luna" }
    }
}

function Set-SelectedEngine {
    param([Parameter(Mandatory = $true)][ValidateSet("LOCAL","LUNA")][string]$Engine)

    if ($script:LocalRunning -or (($null -ne $script:BackendProcess) -and (-not $script:BackendProcess.HasExited))) {
        return
    }

    if ($script:SelectedEngine -ne $Engine) {
        $script:ChatMessages.Clear()
        if (($null -ne $script:ChatForm) -and (-not $script:ChatForm.IsDisposed)) {
            $script:ChatForm.Close()
        }
        $script:ChatForm = $null
    }

    $script:SelectedEngine = $Engine
    Update-SelectedEngineDisplay
    Append-Log ("[KADENCE UI] Selected engine: {0}. No fallback is configured." -f $Engine)
}

function Show-KadenceChat {
    if (($null -ne $script:ChatForm) -and (-not $script:ChatForm.IsDisposed)) {
        $script:ChatForm.Activate()
        return
    }

    $chatForm = New-Object System.Windows.Forms.Form
    $chatForm.Text = ("Kadence Chat - {0}" -f $script:SelectedEngine)
    $chatForm.StartPosition = "CenterParent"
    $chatForm.Size = New-Object System.Drawing.Size(760,620)
    $chatForm.MinimumSize = New-Object System.Drawing.Size(620,480)
    $chatForm.BackColor = $ColorBg
    $chatForm.ForeColor = $ColorText
    $chatForm.Font = New-Font 10
    $chatForm.Owner = $form
    $script:ChatForm = $chatForm

    $chatHeader = New-Object System.Windows.Forms.Label
    $chatHeader.Dock = "Top"
    $chatHeader.Height = 44
    $chatHeader.Padding = New-Object System.Windows.Forms.Padding(14,0,0,0)
    $chatHeader.TextAlign = "MiddleLeft"
    $chatHeader.Text = ("KADENCE TEXT SESSION  //  {0}" -f $script:SelectedEngine)
    $chatHeader.ForeColor = $ColorCyan
    $chatHeader.BackColor = $ColorPanel
    $chatHeader.Font = New-Font 10 ([System.Drawing.FontStyle]::Bold)
    $chatForm.Controls.Add($chatHeader)

    $chatStatus = New-Object System.Windows.Forms.Label
    $chatStatus.Dock = "Bottom"
    $chatStatus.Height = 28
    $chatStatus.Padding = New-Object System.Windows.Forms.Padding(12,0,0,0)
    $chatStatus.TextAlign = "MiddleLeft"
    $chatStatus.Text = "Control Surface text context is separate from the robot voice session."
    $chatStatus.ForeColor = $ColorMuted
    $chatStatus.BackColor = $ColorPanel
    $chatStatus.Font = New-Font 8
    $chatForm.Controls.Add($chatStatus)

    $inputPanel = New-Object System.Windows.Forms.Panel
    $inputPanel.Dock = "Bottom"
    $inputPanel.Height = 54
    $inputPanel.Padding = New-Object System.Windows.Forms.Padding(10,8,10,8)
    $inputPanel.BackColor = $ColorPanel
    $chatForm.Controls.Add($inputPanel)

    $sendButton = New-Object System.Windows.Forms.Button
    $sendButton.Dock = "Right"
    $sendButton.Width = 92
    $sendButton.Text = "SEND"
    $sendButton.FlatStyle = "Flat"
    $sendButton.FlatAppearance.BorderColor = $ColorCyan
    $sendButton.BackColor = $ColorPanelAlt
    $sendButton.ForeColor = $ColorCyan
    $sendButton.Font = New-Font 9 ([System.Drawing.FontStyle]::Bold)
    $inputPanel.Controls.Add($sendButton)

    $chatInput = New-Object System.Windows.Forms.TextBox
    $chatInput.Dock = "Fill"
    $chatInput.BackColor = [System.Drawing.Color]::FromArgb(4,7,10)
    $chatInput.ForeColor = $ColorText
    $chatInput.BorderStyle = "FixedSingle"
    $chatInput.Font = New-Font 10
    $inputPanel.Controls.Add($chatInput)

    $transcript = New-Object System.Windows.Forms.RichTextBox
    $transcript.Dock = "Fill"
    $transcript.ReadOnly = $true
    $transcript.WordWrap = $true
    $transcript.BackColor = [System.Drawing.Color]::FromArgb(4,7,10)
    $transcript.ForeColor = $ColorText
    $transcript.BorderStyle = "None"
    $transcript.Font = New-Font 10 ([System.Drawing.FontStyle]::Regular) "Segoe UI"
    $transcript.Padding = New-Object System.Windows.Forms.Padding(10)
    $chatForm.Controls.Add($transcript)
    $transcript.BringToFront()

    foreach ($HistoryItem in @($script:ChatMessages)) {
        $Prefix = if ([string]$HistoryItem.role -eq "user") { "YOU" } else { "KADENCE" }
        $transcript.AppendText(("{0}> {1}`r`n`r`n" -f $Prefix,[string]$HistoryItem.content))
    }

    $SendAction = {
        $Text = $chatInput.Text.Trim()
        if ([string]::IsNullOrWhiteSpace($Text)) { return }

        $EngineRunning = if ($script:SelectedEngine -eq "LOCAL") {
            $script:LocalRunning
        } else {
            (($null -ne $script:BackendProcess) -and (-not $script:BackendProcess.HasExited))
        }
        if (-not $EngineRunning) {
            $chatStatus.Text = ("{0} is not running." -f $script:SelectedEngine)
            $chatStatus.ForeColor = $ColorRed
            return
        }

        $chatInput.Clear()
        $transcript.AppendText(("YOU> {0}`r`n`r`n" -f $Text))
        $transcript.SelectionStart = $transcript.TextLength
        $transcript.ScrollToCaret()
        $script:ChatMessages.Add([pscustomobject]@{ role = "user"; content = $Text })

        while ($script:ChatMessages.Count -gt 16) {
            $script:ChatMessages.RemoveAt(0)
        }

        $sendButton.Enabled = $false
        $chatInput.Enabled = $false
        $chatStatus.Text = ("{0} is thinking..." -f $script:SelectedEngine)
        $chatStatus.ForeColor = $ColorAmber
        [System.Windows.Forms.Application]::DoEvents()

        try {
            $History = @($script:ChatMessages | ForEach-Object { $_ })
            $Result = & $ControlChatScript -Engine $script:SelectedEngine -Messages $History
            $Reply = [string]$Result.Text
            $script:ChatMessages.Add([pscustomobject]@{ role = "assistant"; content = $Reply })
            while ($script:ChatMessages.Count -gt 16) {
                $script:ChatMessages.RemoveAt(0)
            }

            $transcript.AppendText(("KADENCE> {0}`r`n`r`n" -f $Reply))
            $transcript.SelectionStart = $transcript.TextLength
            $transcript.ScrollToCaret()
            $chatStatus.Text = ("{0} / {1} / {2:N0} ms" -f $Result.Engine,$Result.Model,[double]$Result.WallMilliseconds)
            $chatStatus.ForeColor = $ColorTeal
        }
        catch {
            $transcript.AppendText(("[ERROR] {0}`r`n`r`n" -f $_.Exception.Message))
            $transcript.SelectionStart = $transcript.TextLength
            $transcript.ScrollToCaret()
            $chatStatus.Text = "Chat request failed. No alternate engine was attempted."
            $chatStatus.ForeColor = $ColorRed
        }
        finally {
            $sendButton.Enabled = $true
            $chatInput.Enabled = $true
            $chatInput.Focus()
        }
    }.GetNewClosure()

    $sendButton.add_Click($SendAction)
    $chatInput.add_KeyDown({
        param($sender,$e)
        if ($e.KeyCode -eq [System.Windows.Forms.Keys]::Enter) {
            $e.SuppressKeyPress = $true
            & $SendAction
        }
    })

    $chatForm.add_FormClosed({ $script:ChatForm = $null })
    $chatForm.Show($form)
    $chatInput.Focus()
}
'@
$Working = Replace-Required -Text $Working -From $SetEyeNeedle.TrimEnd() -To $Alpha3Functions.TrimEnd() -Label 'Alpha 3 engine/chat functions'

# --- Engine-specific port preflight ----------------------------------------
$PortFunctionNeedle = @'
function Get-PortConflicts {
    $items = New-Object System.Collections.Generic.List[object]
'@
$PortFunctionBlock = @'
function Get-PortConflicts {
    $items = New-Object System.Collections.Generic.List[object]

    if ($script:SelectedEngine -eq "LOCAL") {
        $localTcp = Get-NetTCPConnection -State Listen -LocalPort 11434 -ErrorAction SilentlyContinue
        foreach ($entry in @($localTcp)) {
            if ($null -ne $entry) {
                $items.Add([pscustomobject]@{Protocol="TCP";Port=11434;Pid=$entry.OwningProcess})
            }
        }
        return $items
    }
'@
$Working = Replace-Required -Text $Working -From $PortFunctionNeedle.TrimEnd() -To $PortFunctionBlock.TrimEnd() -Label 'LOCAL port preflight'

# --- LOCAL start path; existing Alpha 2 path remains the LUNA branch -------
$StartFunctionNeedle = 'function Start-Backend {'
$StartFunctionBlock = @'
function Start-Backend {
    if ($script:SelectedEngine -eq "LOCAL") {
        if ($script:LocalRunning) { return }

        $conflicts = @(Get-PortConflicts)
        if ($conflicts.Count -gt 0) {
            Append-Log "[KADENCE UI] LOCAL START BLOCKED: TCP 11434 is already in use."
            foreach ($c in $conflicts) {
                Append-Log ("[KADENCE UI] {0} {1} busy - {2}" -f $c.Protocol,$c.Port,(Describe-Process -ProcessId $c.Pid))
            }
            Append-Log "[KADENCE UI] Kadence will not hijack an existing Ollama service."
            $stateLabel.Text = "PORT CONFLICT"; $stateLabel.ForeColor = $ColorRed
            $serverHealth.Text = "LOCAL  BLOCKED"; $serverHealth.ForeColor = $ColorRed
            Set-EyeState "error"
            return
        }

        $script:StopRequested = $false
        $stateLabel.Text = "INITIALISING LOCAL"; $stateLabel.ForeColor = $ColorAmber
        $serverHealth.Text = "LOCAL  BOOTING"; $serverHealth.ForeColor = $ColorAmber
        $robotHealth.Text = "ROBOT  DEFERRED"; $robotHealth.ForeColor = $ColorOffline
        $asrHealth.Text = "ASR  DEFERRED"; $asrHealth.ForeColor = $ColorOffline
        Set-EyeState "booting"
        Set-EngineSelectionEnabled $false
        $startButton.Enabled = $false; $startButton.ForeColor = $ColorOffline
        $stopButton.Enabled = $true; $stopButton.ForeColor = $ColorRed; $stopButton.FlatAppearance.BorderColor = $ColorRed
        $chatButton.Enabled = $false; $chatButton.ForeColor = $ColorOffline; $chatButton.FlatAppearance.BorderColor = $ColorOffline
        Append-Log "[KADENCE UI] Starting LOCAL / qwen3.5:4b. No LUNA fallback is configured."

        try {
            $LocalOutput = @(& $LocalStartScript 2>&1 | Out-String -Stream)
            foreach ($LocalLine in $LocalOutput) {
                if (-not [string]::IsNullOrWhiteSpace([string]$LocalLine)) { Append-Log ([string]$LocalLine) }
            }

            $script:LocalRunning = $true
            $serverHealth.Text = "LOCAL  READY"; $serverHealth.ForeColor = $ColorTeal
            $robotHealth.Text = "ROBOT  DEFERRED"; $robotHealth.ForeColor = $ColorOffline
            $asrHealth.Text = "ASR  DEFERRED"; $asrHealth.ForeColor = $ColorOffline
            $transportHealth.Text = "TRANSPORT  DEFERRED"; $transportHealth.ForeColor = $ColorOffline
            $stateLabel.Text = "KADENCE LOCAL"; $stateLabel.ForeColor = $ColorTeal
            $chatButton.Enabled = $true; $chatButton.ForeColor = $ColorCyan; $chatButton.FlatAppearance.BorderColor = $ColorCyan
            Set-EyeState "online"
            Append-Log "[KADENCE UI] LOCAL ready. Control Surface text chat is available."
        }
        catch {
            Append-Log ("[KADENCE UI] LOCAL START FAILED: " + $_.Exception.Message)
            $script:LocalRunning = $false
            $serverHealth.Text = "LOCAL  FAILED"; $serverHealth.ForeColor = $ColorRed
            $stateLabel.Text = "START FAILED"; $stateLabel.ForeColor = $ColorRed
            $startButton.Enabled = $true; $startButton.ForeColor = $ColorCyan
            $stopButton.Enabled = $false; $stopButton.ForeColor = $ColorOffline; $stopButton.FlatAppearance.BorderColor = $ColorOffline
            $chatButton.Enabled = $false
            Set-EngineSelectionEnabled $true
            Set-EyeState "error"
        }
        return
    }
'@
$Working = Replace-Required -Text $Working -From $StartFunctionNeedle -To $StartFunctionBlock.TrimEnd() -Label 'LOCAL start branch'

$Working = Replace-Required -Text $Working `
    -From '    Append-Log "[KADENCE UI] Starting Alpha 2 backend..."' `
    -To ('    Set-EngineSelectionEnabled $false' + $Nl +
         '    $chatButton.Enabled = $false' + $Nl +
         '    Append-Log "[KADENCE UI] Starting LUNA / frozen Alpha 2 backend. No LOCAL fallback is configured."') `
    -Label 'LUNA start label / selection lock'

$Working = Replace-Required -Text $Working `
    -From '        $serverHealth.Text = "SERVER  ONLINE"; $serverHealth.ForeColor = $ColorCyan' `
    -To ('        $serverHealth.Text = "SERVER  ONLINE"; $serverHealth.ForeColor = $ColorCyan' + $Nl +
         '        $chatButton.Enabled = $true; $chatButton.ForeColor = $ColorCyan; $chatButton.FlatAppearance.BorderColor = $ColorCyan') `
    -Label 'LUNA chat enable on server online'

# Re-enable selection whenever the original LUNA path returns to idle/failure.
$IdleButtonPair = @'
        $startButton.Enabled = $true; $startButton.ForeColor = $ColorCyan
        $stopButton.Enabled = $false; $stopButton.ForeColor = $ColorOffline; $stopButton.FlatAppearance.BorderColor = $ColorOffline
'@
$IdleButtonPairAlpha3 = @'
        $startButton.Enabled = $true; $startButton.ForeColor = $ColorCyan
        $stopButton.Enabled = $false; $stopButton.ForeColor = $ColorOffline; $stopButton.FlatAppearance.BorderColor = $ColorOffline
        $chatButton.Enabled = $false; $chatButton.ForeColor = $ColorOffline; $chatButton.FlatAppearance.BorderColor = $ColorOffline
        Set-EngineSelectionEnabled $true
'@
if (-not $Working.Contains($IdleButtonPair.TrimEnd())) {
    throw "Alpha 3 Control Surface patch guard failed: idle button state"
}
$Working = $Working.Replace($IdleButtonPair.TrimEnd(), $IdleButtonPairAlpha3.TrimEnd())

# --- LOCAL stop branch ------------------------------------------------------
$StopFunctionNeedle = @'
function Stop-Backend {
    param([bool]$Silent = $false)
'@
$StopFunctionBlock = @'
function Stop-Backend {
    param([bool]$Silent = $false)

    if ($script:LocalRunning) {
        $script:StopRequested = $true
        $stateLabel.Text = "SHUTTING DOWN"; $stateLabel.ForeColor = $ColorAmber
        $serverHealth.Text = "LOCAL  STOPPING"; $serverHealth.ForeColor = $ColorAmber
        Set-EyeState "booting"
        if (-not $Silent) { Append-Log "[KADENCE UI] Stopping Project-owned LOCAL runtime..." }

        try {
            $StopOutput = @(& $LocalStopScript 2>&1 | Out-String -Stream)
            foreach ($StopLine in $StopOutput) {
                if (-not [string]::IsNullOrWhiteSpace([string]$StopLine)) { Append-Log ([string]$StopLine) }
            }
            $script:LocalRunning = $false
            Set-OfflineState
            Update-SelectedEngineDisplay
            $startButton.Enabled = $true; $startButton.ForeColor = $ColorCyan
            $stopButton.Enabled = $false; $stopButton.ForeColor = $ColorOffline; $stopButton.FlatAppearance.BorderColor = $ColorOffline
            $chatButton.Enabled = $false; $chatButton.ForeColor = $ColorOffline; $chatButton.FlatAppearance.BorderColor = $ColorOffline
            Set-EngineSelectionEnabled $true
            if (-not $Silent) { Append-Log "[KADENCE UI] LOCAL stopped; TCP 11434 released." }
        }
        catch {
            Append-Log ("[KADENCE UI] LOCAL STOP FAILED: " + $_.Exception.Message)
            $stateLabel.Text = "STOP FAILED"; $stateLabel.ForeColor = $ColorRed
            Set-EyeState "error"
        }
        return
    }
'@
$Working = Replace-Required -Text $Working -From $StopFunctionNeedle.TrimEnd() -To $StopFunctionBlock.TrimEnd() -Label 'LOCAL stop branch'

# --- LOCAL unexpected-exit monitor -----------------------------------------
$TimerNeedle = @'
$timer.add_Tick({
    try {
'@
$TimerBlock = @'
$timer.add_Tick({
    try {
        if ($script:LocalRunning) {
            $LocalListener = @(Get-NetTCPConnection -State Listen -LocalPort 11434 -ErrorAction SilentlyContinue)
            if ($LocalListener.Count -eq 0) {
                $script:LocalRunning = $false
                Append-Log "[KADENCE UI] LOCAL runtime disappeared unexpectedly; no alternate engine will be started."
                $serverHealth.Text = "LOCAL  EXITED"; $serverHealth.ForeColor = $ColorRed
                $stateLabel.Text = "LOCAL EXITED"; $stateLabel.ForeColor = $ColorRed
                $startButton.Enabled = $true; $startButton.ForeColor = $ColorCyan
                $stopButton.Enabled = $false; $stopButton.ForeColor = $ColorOffline; $stopButton.FlatAppearance.BorderColor = $ColorOffline
                $chatButton.Enabled = $false; $chatButton.ForeColor = $ColorOffline; $chatButton.FlatAppearance.BorderColor = $ColorOffline
                Set-EngineSelectionEnabled $true
                Set-EyeState "error"
            }
        }
'@
$Working = Replace-Required -Text $Working -From $TimerNeedle.TrimEnd() -To $TimerBlock.TrimEnd() -Label 'LOCAL runtime monitor'

# --- Operator events / close semantics -------------------------------------
$ClickNeedle = @'
$startButton.add_Click({ Start-Backend })
$stopButton.add_Click({ Stop-Backend })
$clearButton.add_Click({ $logBox.Clear() })
'@
$ClickBlock = @'
$startButton.add_Click({ Start-Backend })
$stopButton.add_Click({ Stop-Backend })
$chatButton.add_Click({ Show-KadenceChat })
$localEngineButton.add_Click({ Set-SelectedEngine -Engine "LOCAL" })
$lunaEngineButton.add_Click({ Set-SelectedEngine -Engine "LUNA" })
$clearButton.add_Click({ $logBox.Clear() })
'@
$Working = Replace-Required -Text $Working -From $ClickNeedle.TrimEnd() -To $ClickBlock.TrimEnd() -Label 'Alpha 3 operator events'

$Working = Replace-Required -Text $Working `
    -From '    if (($null -ne $script:BackendProcess) -and (-not $script:BackendProcess.HasExited)) {' `
    -To '    if ($script:LocalRunning -or (($null -ne $script:BackendProcess) -and (-not $script:BackendProcess.HasExited))) {' `
    -Label 'form-close active-engine guard'
$Working = Replace-Required -Text $Working `
    -From '        $answer = [System.Windows.Forms.MessageBox]::Show("The Kadence backend is still running. Stop it and exit?","Kadence Control Surface",[System.Windows.Forms.MessageBoxButtons]::YesNo,[System.Windows.Forms.MessageBoxIcon]::Question)' `
    -To '        $answer = [System.Windows.Forms.MessageBox]::Show("The selected Kadence engine is still running. Stop it and exit?","Kadence Control Surface",[System.Windows.Forms.MessageBoxButtons]::YesNo,[System.Windows.Forms.MessageBoxIcon]::Question)' `
    -Label 'form-close message'

# V4 already removed the legacy profile controls from the visible surface. Alpha
# 3 now initialises an explicit engine selection instead of reading retired state.
$Working = Replace-Required -Text $Working `
    -From 'Append-Log "[KADENCE UI] Control Surface V4 ready."' `
    -To ('Set-SelectedEngine -Engine "LOCAL"' + $Nl +
         'Append-Log "[KADENCE UI] Control Surface Alpha 3 ready: explicit LOCAL / LUNA selection, no AUTO, no fallback."' + $Nl +
         'Append-Log "[KADENCE UI] CHAT opens a Control-Surface text session on the selected running engine."') `
    -Label 'Alpha 3 initial engine selection'

foreach ($RequiredMarker in @(
    '$script:SelectedEngine = "LOCAL"',
    '$LocalStartScript = Join-Path $BackendRoot "start_local_windows.ps1"',
    '$ControlChatScript = Join-Path $BackendRoot "invoke_control_chat_windows.ps1"',
    '$localEngineButton.Text = "LOCAL"',
    '$lunaEngineButton.Text = "LUNA"',
    '$chatButton.Text = "CHAT"',
    'No LUNA fallback is configured.',
    'No LOCAL fallback is configured.',
    'Control Surface text context is separate from the robot voice session.'
)) {
    if (-not $Working.Contains($RequiredMarker)) {
        throw "Alpha 3 Control Surface post-patch verification failed: $RequiredMarker"
    }
}

if ($Working.Contains('AUTO')) {
    throw "Alpha 3 Control Surface verification found forbidden AUTO routing text."
}

return $Working
