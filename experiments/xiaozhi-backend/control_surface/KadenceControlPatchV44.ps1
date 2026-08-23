param(
    [Parameter(Mandatory = $true)][string]$UiText
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

# Alpha 2 M7: exactly two session-behaviour states.
# DEFAULT = canonical Kadence unchanged.
# CUSTOM = one explicit, volatile free-text behaviour overlay (max 1000 chars).
# The backend owns state in RAM and exposes only a loopback control endpoint.

# ---------------------------------------------------------------------------
# Control-plane state and geometry.
# ---------------------------------------------------------------------------
$UiText = $UiText.Replace(
    '$CmdExe = Join-Path $env:SystemRoot "System32\cmd.exe"',
    @'
$CmdExe = Join-Path $env:SystemRoot "System32\cmd.exe"
$BehaviorPort = 8766
$BehaviorUri = "http://127.0.0.1:$BehaviorPort/v1/behavior"
'@.TrimEnd()
)

$UiText = $UiText.Replace(
    '$script:EyeState = "offline"',
    @'
$script:EyeState = "offline"
$script:BehaviorReady = $false
'@.TrimEnd()
)

# Give the new M7 card room without shrinking the live log into uselessness.
$UiText = $UiText.Replace(
    '$form.Size = New-Object System.Drawing.Size(1360,860)',
    '$form.Size = New-Object System.Drawing.Size(1360,940)'
)
$UiText = $UiText.Replace(
    '$form.MinimumSize = New-Object System.Drawing.Size(1180,740)',
    '$form.MinimumSize = New-Object System.Drawing.Size(1180,820)'
)

# ---------------------------------------------------------------------------
# Insert the M7 behaviour card immediately before the live-log section.
# ---------------------------------------------------------------------------
$BehaviorAnchor = '$logTitle = New-Object System.Windows.Forms.Label'
$BehaviorBlock = @'
$behaviorTitle = New-Object System.Windows.Forms.Label
$behaviorTitle.AutoSize = $true
$behaviorTitle.Text = "SESSION BEHAVIOUR"
$behaviorTitle.Font = New-Font 9 ([System.Drawing.FontStyle]::Bold)
$behaviorTitle.ForeColor = $ColorMuted
$behaviorTitle.Location = New-Object System.Drawing.Point(24,282)
$right.Controls.Add($behaviorTitle)

$behaviorStatus = New-Object System.Windows.Forms.Label
$behaviorStatus.AutoSize = $false
$behaviorStatus.Size = New-Object System.Drawing.Size(180,22)
$behaviorStatus.Location = New-Object System.Drawing.Point(564,278)
$behaviorStatus.Anchor = "Top,Right"
$behaviorStatus.Text = "DEFAULT"
$behaviorStatus.TextAlign = "MiddleRight"
$behaviorStatus.ForeColor = $ColorCyan
$behaviorStatus.Font = New-Font 8 ([System.Drawing.FontStyle]::Bold)
$right.Controls.Add($behaviorStatus)

$behaviorPanel = New-Object System.Windows.Forms.Panel
$behaviorPanel.Location = New-Object System.Drawing.Point(24,308)
$behaviorPanel.Size = New-Object System.Drawing.Size(720,138)
$behaviorPanel.Anchor = "Top,Left,Right"
$behaviorPanel.BackColor = $ColorPanelAlt
$behaviorPanel.BorderStyle = "FixedSingle"
$right.Controls.Add($behaviorPanel)

$defaultBehaviorButton = New-Object System.Windows.Forms.Button
$defaultBehaviorButton.Text = "DEFAULT"
$defaultBehaviorButton.Location = New-Object System.Drawing.Point(12,12)
$defaultBehaviorButton.Size = New-Object System.Drawing.Size(122,34)
$defaultBehaviorButton.FlatStyle = "Flat"
$defaultBehaviorButton.FlatAppearance.BorderColor = $ColorCyan
$defaultBehaviorButton.FlatAppearance.BorderSize = 1
$defaultBehaviorButton.BackColor = $ColorPanel
$defaultBehaviorButton.ForeColor = $ColorOffline
$defaultBehaviorButton.Font = New-Font 9 ([System.Drawing.FontStyle]::Bold)
$defaultBehaviorButton.Enabled = $false
$behaviorPanel.Controls.Add($defaultBehaviorButton)

$customBehaviorLabel = New-Object System.Windows.Forms.Label
$customBehaviorLabel.AutoSize = $true
$customBehaviorLabel.Text = "CUSTOM"
$customBehaviorLabel.Location = New-Object System.Drawing.Point(148,20)
$customBehaviorLabel.ForeColor = $ColorMuted
$customBehaviorLabel.Font = New-Font 8 ([System.Drawing.FontStyle]::Bold)
$behaviorPanel.Controls.Add($customBehaviorLabel)

$customBehaviorCount = New-Object System.Windows.Forms.Label
$customBehaviorCount.AutoSize = $false
$customBehaviorCount.Size = New-Object System.Drawing.Size(120,20)
$customBehaviorCount.Location = New-Object System.Drawing.Point(584,18)
$customBehaviorCount.Anchor = "Top,Right"
$customBehaviorCount.Text = "0 / 1000"
$customBehaviorCount.TextAlign = "MiddleRight"
$customBehaviorCount.ForeColor = $ColorOffline
$customBehaviorCount.Font = New-Font 8
$behaviorPanel.Controls.Add($customBehaviorCount)

$customBehaviorBox = New-Object System.Windows.Forms.TextBox
$customBehaviorBox.Location = New-Object System.Drawing.Point(12,56)
$customBehaviorBox.Size = New-Object System.Drawing.Size(548,66)
$customBehaviorBox.Anchor = "Top,Left,Right"
$customBehaviorBox.Multiline = $true
$customBehaviorBox.ScrollBars = "Vertical"
$customBehaviorBox.MaxLength = 1000
$customBehaviorBox.BackColor = [System.Drawing.Color]::FromArgb(4,7,10)
$customBehaviorBox.ForeColor = $ColorText
$customBehaviorBox.BorderStyle = "FixedSingle"
$customBehaviorBox.Font = New-Font 9
$customBehaviorBox.Enabled = $false
$behaviorPanel.Controls.Add($customBehaviorBox)

$applyCustomButton = New-Object System.Windows.Forms.Button
$applyCustomButton.Text = "APPLY CUSTOM"
$applyCustomButton.Location = New-Object System.Drawing.Point(572,56)
$applyCustomButton.Size = New-Object System.Drawing.Size(132,66)
$applyCustomButton.Anchor = "Top,Right"
$applyCustomButton.FlatStyle = "Flat"
$applyCustomButton.FlatAppearance.BorderColor = $ColorCyan
$applyCustomButton.FlatAppearance.BorderSize = 1
$applyCustomButton.BackColor = $ColorPanel
$applyCustomButton.ForeColor = $ColorOffline
$applyCustomButton.Font = New-Font 9 ([System.Drawing.FontStyle]::Bold)
$applyCustomButton.Enabled = $false
$behaviorPanel.Controls.Add($applyCustomButton)

$logTitle = New-Object System.Windows.Forms.Label
'@
if (-not $UiText.Contains($BehaviorAnchor)) {
    throw "Kadence Control V4.4 behaviour-card anchor was not found."
}
$UiText = $UiText.Replace($BehaviorAnchor, $BehaviorBlock.TrimEnd())

# Move the live log below the behaviour card.
$UiText = $UiText.Replace(
    '$logTitle.Location = New-Object System.Drawing.Point(24,282)',
    '$logTitle.Location = New-Object System.Drawing.Point(24,466)'
)
$UiText = $UiText.Replace(
    '$clearButton.Location = New-Object System.Drawing.Point(666,270)',
    '$clearButton.Location = New-Object System.Drawing.Point(666,454)'
)
$UiText = $UiText.Replace(
    '$logFrame.Location = New-Object System.Drawing.Point(24,314)',
    '$logFrame.Location = New-Object System.Drawing.Point(24,498)'
)
$UiText = $UiText.Replace(
    '$logFrame.Size = New-Object System.Drawing.Size(720,390)',
    '$logFrame.Size = New-Object System.Drawing.Size(720,270)'
)
$UiText = $UiText.Replace(
    '$logBox.Size = New-Object System.Drawing.Size(718,388)',
    '$logBox.Size = New-Object System.Drawing.Size(718,268)'
)

# Keep the new card/status aligned when the right pane resizes.
$UiText = $UiText.Replace(
    '    $lastTurn.Width = $width' + [Environment]::NewLine + '    $logFrame.Width = $width',
    '    $lastTurn.Width = $width' + [Environment]::NewLine + '    $behaviorPanel.Width = $width' + [Environment]::NewLine + '    $behaviorStatus.Left = $right.ClientSize.Width - 204' + [Environment]::NewLine + '    $logFrame.Width = $width'
)

# ---------------------------------------------------------------------------
# Local control client helpers. No prompt text is written to disk or logged.
# ---------------------------------------------------------------------------
$FunctionAnchor = 'function Set-OfflineState {'
$FunctionBlock = @'
function Set-BehaviorControlsReady {
    param([bool]$Ready)
    $script:BehaviorReady = $Ready
    $defaultBehaviorButton.Enabled = $Ready
    $applyCustomButton.Enabled = $Ready
    $customBehaviorBox.Enabled = $Ready
    if ($Ready) {
        $defaultBehaviorButton.ForeColor = $ColorCyan
        $applyCustomButton.ForeColor = $ColorCyan
    } else {
        $defaultBehaviorButton.ForeColor = $ColorOffline
        $applyCustomButton.ForeColor = $ColorOffline
    }
}

function Set-BehaviorUiDefault {
    $behaviorStatus.Text = "DEFAULT"
    $behaviorStatus.ForeColor = $ColorCyan
    $defaultBehaviorButton.FlatAppearance.BorderColor = $ColorCyan
    $applyCustomButton.FlatAppearance.BorderColor = $ColorCyan
}

function Invoke-KadenceBehaviorControl {
    param([Parameter(Mandatory = $true)][hashtable]$Payload)

    $json = $Payload | ConvertTo-Json -Compress
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($json)
    $request = [System.Net.HttpWebRequest]::Create($BehaviorUri)
    $request.Method = "POST"
    $request.ContentType = "application/json; charset=utf-8"
    $request.ContentLength = $bytes.Length
    $request.Timeout = 1800
    $request.ReadWriteTimeout = 1800
    $request.Proxy = $null

    $stream = $request.GetRequestStream()
    try {
        $stream.Write($bytes,0,$bytes.Length)
    }
    finally {
        $stream.Dispose()
    }

    try {
        $response = $request.GetResponse()
    }
    catch [System.Net.WebException] {
        $message = $_.Exception.Message
        if ($null -ne $_.Exception.Response) {
            try {
                $reader = New-Object System.IO.StreamReader($_.Exception.Response.GetResponseStream())
                $body = $reader.ReadToEnd()
                $reader.Dispose()
                if (-not [string]::IsNullOrWhiteSpace($body)) { $message = $body }
            }
            catch {}
        }
        throw "M7 behaviour control request failed: $message"
    }

    try {
        $reader = New-Object System.IO.StreamReader($response.GetResponseStream(),[System.Text.Encoding]::UTF8)
        $body = $reader.ReadToEnd()
        $reader.Dispose()
        if ([string]::IsNullOrWhiteSpace($body)) {
            throw "M7 behaviour control returned an empty response."
        }
        return ($body | ConvertFrom-Json)
    }
    finally {
        $response.Dispose()
    }
}

function Set-OfflineState {
'@
if (-not $UiText.Contains($FunctionAnchor)) {
    throw "Kadence Control V4.4 helper anchor was not found."
}
$UiText = $UiText.Replace($FunctionAnchor, $FunctionBlock.TrimEnd())

# Backend stop/exit means process-owned behaviour state is gone. Reflect that
# immediately and erase stale text so the UI cannot imply it will survive boot.
$UiText = $UiText.Replace(
    'function Set-OfflineState {' + [Environment]::NewLine + '    $script:RobotConnected = $false',
    'function Set-OfflineState {' + [Environment]::NewLine + '    $script:RobotConnected = $false' + [Environment]::NewLine + '    Set-BehaviorControlsReady $false' + [Environment]::NewLine + '    Set-BehaviorUiDefault' + [Environment]::NewLine + '    $customBehaviorBox.Clear()'
)

# Add the loopback control port to the existing deliberate preflight.
$UiText = $UiText.Replace(
    'foreach ($port in @(8000,8003)) {',
    'foreach ($port in @(8000,8003,8766)) {'
)
$UiText = $UiText.Replace(
    'Preflight protects UDP 45872 and TCP 8000/8003;',
    'Preflight protects UDP 45872 and TCP 8000/8003/8766;'
)

# On every backend start, clear the editor and show DEFAULT before launch. The
# Python process also hard-resets its own in-memory state, so UI and backend agree.
$UiText = $UiText.Replace(
    '    $script:RobotConnected = $false' + [Environment]::NewLine + '    $lastTurn.Text = "-"',
    '    $script:RobotConnected = $false' + [Environment]::NewLine + '    Set-BehaviorControlsReady $false' + [Environment]::NewLine + '    Set-BehaviorUiDefault' + [Environment]::NewLine + '    $customBehaviorBox.Clear()' + [Environment]::NewLine + '    $lastTurn.Text = "-"'
)

# Enable M7 controls only after the backend reports its loopback control plane.
$ProcessAnchor = '    Append-Log $Line'
$ProcessBlock = @'
    Append-Log $Line

    if ($Line -match 'KADENCE BEHAVIOR: control ready .* mode=default') {
        Set-BehaviorControlsReady $true
        Set-BehaviorUiDefault
        $behaviorStatus.Text = "DEFAULT"
        Append-Log "[KADENCE UI] M7 behaviour control ready / DEFAULT."
    }
    elseif ($Line -match 'KADENCE BEHAVIOR: custom applied chars=([0-9]+)') {
        $behaviorStatus.Text = "CUSTOM ACTIVE"
        $behaviorStatus.ForeColor = $ColorAmber
    }
    elseif ($Line -match 'KADENCE BEHAVIOR: default restored') {
        Set-BehaviorUiDefault
    }
'@
if (-not $UiText.Contains($ProcessAnchor)) {
    throw "Kadence Control V4.4 server-line anchor was not found."
}
$UiText = $UiText.Replace($ProcessAnchor, $ProcessBlock.TrimEnd())

# ---------------------------------------------------------------------------
# Explicit operator actions. Typing alone never changes live behaviour.
# ---------------------------------------------------------------------------
$EventAnchor = '$startButton.add_Click({ Start-Backend })'
$EventBlock = @'
$customBehaviorBox.add_TextChanged({
    $customBehaviorCount.Text = ("{0} / 1000" -f $customBehaviorBox.TextLength)
})

$defaultBehaviorButton.add_Click({
    if (-not $script:BehaviorReady) { return }
    try {
        $result = Invoke-KadenceBehaviorControl -Payload @{ mode = "default" }
        if (-not $result.ok) { throw "Backend rejected DEFAULT." }
        Set-BehaviorUiDefault
        Append-Log "[KADENCE UI] M7 behaviour: DEFAULT applied."
    }
    catch {
        $behaviorStatus.Text = "CONTROL ERROR"
        $behaviorStatus.ForeColor = $ColorRed
        Append-Log ("[KADENCE UI] M7 DEFAULT FAILED: " + $_.Exception.Message)
    }
})

$applyCustomButton.add_Click({
    if (-not $script:BehaviorReady) { return }
    $custom = $customBehaviorBox.Text.Trim()
    if ([string]::IsNullOrWhiteSpace($custom)) {
        Append-Log "[KADENCE UI] M7 CUSTOM not applied: enter a behaviour prompt first."
        return
    }
    if ($custom.Length -gt 1000) {
        Append-Log "[KADENCE UI] M7 CUSTOM not applied: 1000-character limit exceeded."
        return
    }

    try {
        $result = Invoke-KadenceBehaviorControl -Payload @{ mode = "custom"; prompt = $custom }
        if (-not $result.ok) { throw "Backend rejected CUSTOM." }
        $behaviorStatus.Text = "CUSTOM ACTIVE"
        $behaviorStatus.ForeColor = $ColorAmber
        Append-Log ("[KADENCE UI] M7 behaviour: CUSTOM applied ({0} chars)." -f $custom.Length)
    }
    catch {
        $behaviorStatus.Text = "CONTROL ERROR"
        $behaviorStatus.ForeColor = $ColorRed
        Append-Log ("[KADENCE UI] M7 CUSTOM FAILED: " + $_.Exception.Message)
    }
})

$startButton.add_Click({ Start-Backend })
'@
if (-not $UiText.Contains($EventAnchor)) {
    throw "Kadence Control V4.4 event anchor was not found."
}
$UiText = $UiText.Replace($EventAnchor, $EventBlock.TrimEnd())

# Unexpected process exit does not necessarily call Set-OfflineState in V3;
# explicitly clear M7 UI state in the common exit branch too.
$UiText = $UiText.Replace(
    '            $startButton.Enabled = $true; $startButton.ForeColor = $ColorCyan',
    '            Set-BehaviorControlsReady $false' + [Environment]::NewLine + '            Set-BehaviorUiDefault' + [Environment]::NewLine + '            $customBehaviorBox.Clear()' + [Environment]::NewLine + '            $startButton.Enabled = $true; $startButton.ForeColor = $ColorCyan'
)

# Final startup labels.
$UiText = $UiText.Replace(
    'Starting Kadence Control Surface V4.3...',
    'Starting Kadence Control Surface V4.4...'
)
$UiText = $UiText.Replace(
    '[KADENCE UI] Control Surface V4 ready.',
    '[KADENCE UI] Control Surface V4.4 ready.'
)

# Fail closed if the intended M7 surface was not actually injected.
foreach ($RequiredMarker in @(
    '$BehaviorPort = 8766',
    '$customBehaviorBox.MaxLength = 1000',
    'Invoke-KadenceBehaviorControl',
    'mode = "custom"; prompt = $custom',
    'mode = "default"',
    'KADENCE BEHAVIOR: control ready',
    'foreach ($port in @(8000,8003,8766))'
)) {
    if (-not $UiText.Contains($RequiredMarker)) {
        throw "Kadence Control V4.4 post-patch verification failed: $RequiredMarker"
    }
}

return $UiText
