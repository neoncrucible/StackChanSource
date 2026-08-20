param()

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()

$BackendRoot = Split-Path $PSScriptRoot -Parent
$StartScript = Join-Path $BackendRoot "start_alpha2_windows.ps1"
$WindowsPowerShell = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
$CmdExe = Join-Path $env:SystemRoot "System32\cmd.exe"

if (-not (Test-Path $StartScript)) {
    [System.Windows.Forms.MessageBox]::Show("Alpha 2 launcher not found:`r`n$StartScript", "Kadence Control Surface") | Out-Null
    exit 1
}

$script:BackendProcess = $null
$script:BackendLogPath = $null
$script:BackendCmdPath = $null
$script:LogStream = $null
$script:LogReader = $null
$script:StopRequested = $false
$script:ExitReported = $false
$script:RobotConnected = $false
$script:EyeState = "offline"

$ColorBg = [System.Drawing.Color]::FromArgb(5,8,12)
$ColorPanel = [System.Drawing.Color]::FromArgb(12,18,25)
$ColorPanelAlt = [System.Drawing.Color]::FromArgb(17,25,34)
$ColorText = [System.Drawing.Color]::FromArgb(224,235,242)
$ColorMuted = [System.Drawing.Color]::FromArgb(122,146,160)
$ColorCyan = [System.Drawing.Color]::FromArgb(0,217,255)
$ColorTeal = [System.Drawing.Color]::FromArgb(69,255,208)
$ColorAmber = [System.Drawing.Color]::FromArgb(255,176,32)
$ColorRed = [System.Drawing.Color]::FromArgb(255,75,110)
$ColorOffline = [System.Drawing.Color]::FromArgb(72,87,99)

function New-Font {
    param([float]$Size, [System.Drawing.FontStyle]$Style = [System.Drawing.FontStyle]::Regular)
    New-Object System.Drawing.Font("Segoe UI", $Size, $Style)
}

$form = New-Object System.Windows.Forms.Form
$form.Text = "Kadence 2.0 - Control Surface"
$form.StartPosition = "CenterScreen"
$form.Size = New-Object System.Drawing.Size(1120,780)
$form.MinimumSize = New-Object System.Drawing.Size(980,680)
$form.BackColor = $ColorBg
$form.ForeColor = $ColorText
$form.Font = New-Font 10

$header = New-Object System.Windows.Forms.Panel
$header.Dock = "Top"
$header.Height = 76
$header.BackColor = $ColorBg
$form.Controls.Add($header)

$title = New-Object System.Windows.Forms.Label
$title.AutoSize = $true
$title.Text = "PROJECT KADENCE"
$title.Font = New-Font 19 ([System.Drawing.FontStyle]::Bold)
$title.ForeColor = $ColorText
$title.Location = New-Object System.Drawing.Point(24,15)
$header.Controls.Add($title)

$subtitle = New-Object System.Windows.Forms.Label
$subtitle.AutoSize = $true
$subtitle.Text = "ALPHA 2  /  CONTROL SURFACE"
$subtitle.Font = New-Font 9
$subtitle.ForeColor = $ColorCyan
$subtitle.Location = New-Object System.Drawing.Point(27,49)
$header.Controls.Add($subtitle)

$root = New-Object System.Windows.Forms.TableLayoutPanel
$root.Dock = "Fill"
$root.BackColor = $ColorBg
$root.Padding = New-Object System.Windows.Forms.Padding(20,0,20,20)
$root.ColumnCount = 2
$root.RowCount = 1
$root.ColumnStyles.Add((New-Object System.Windows.Forms.ColumnStyle([System.Windows.Forms.SizeType]::Absolute,350))) | Out-Null
$root.ColumnStyles.Add((New-Object System.Windows.Forms.ColumnStyle([System.Windows.Forms.SizeType]::Percent,100))) | Out-Null
$form.Controls.Add($root)

$left = New-Object System.Windows.Forms.Panel
$left.Dock = "Fill"
$left.BackColor = $ColorPanel
$left.Margin = New-Object System.Windows.Forms.Padding(0,0,12,0)
$root.Controls.Add($left,0,0)

$right = New-Object System.Windows.Forms.Panel
$right.Dock = "Fill"
$right.BackColor = $ColorPanel
$right.Margin = New-Object System.Windows.Forms.Padding(0)
$root.Controls.Add($right,1,0)

$eyePanel = New-Object System.Windows.Forms.Panel
$eyePanel.Location = New-Object System.Drawing.Point(20,20)
$eyePanel.Size = New-Object System.Drawing.Size(310,190)
$eyePanel.BackColor = $ColorPanel
$left.Controls.Add($eyePanel)

$stateLabel = New-Object System.Windows.Forms.Label
$stateLabel.Size = New-Object System.Drawing.Size(310,34)
$stateLabel.Location = New-Object System.Drawing.Point(20,214)
$stateLabel.TextAlign = "MiddleCenter"
$stateLabel.Font = New-Font 15 ([System.Drawing.FontStyle]::Bold)
$stateLabel.Text = "SYSTEM OFFLINE"
$stateLabel.ForeColor = $ColorOffline
$left.Controls.Add($stateLabel)

$modeLabel = New-Object System.Windows.Forms.Label
$modeLabel.Size = New-Object System.Drawing.Size(310,24)
$modeLabel.Location = New-Object System.Drawing.Point(20,248)
$modeLabel.TextAlign = "MiddleCenter"
$modeLabel.Font = New-Font 9
$modeLabel.ForeColor = $ColorMuted
$modeLabel.Text = "Canonical identity / Gemini Flash-Lite"
$left.Controls.Add($modeLabel)

$startButton = New-Object System.Windows.Forms.Button
$startButton.Text = "START SERVER"
$startButton.Location = New-Object System.Drawing.Point(20,294)
$startButton.Size = New-Object System.Drawing.Size(150,44)
$startButton.FlatStyle = "Flat"
$startButton.FlatAppearance.BorderColor = $ColorCyan
$startButton.BackColor = $ColorPanelAlt
$startButton.ForeColor = $ColorCyan
$startButton.Font = New-Font 10 ([System.Drawing.FontStyle]::Bold)
$left.Controls.Add($startButton)

$stopButton = New-Object System.Windows.Forms.Button
$stopButton.Text = "STOP SERVER"
$stopButton.Location = New-Object System.Drawing.Point(180,294)
$stopButton.Size = New-Object System.Drawing.Size(150,44)
$stopButton.FlatStyle = "Flat"
$stopButton.FlatAppearance.BorderColor = $ColorOffline
$stopButton.BackColor = $ColorPanelAlt
$stopButton.ForeColor = $ColorOffline
$stopButton.Font = New-Font 10 ([System.Drawing.FontStyle]::Bold)
$stopButton.Enabled = $false
$left.Controls.Add($stopButton)

$divider = New-Object System.Windows.Forms.Label
$divider.Location = New-Object System.Drawing.Point(20,363)
$divider.Size = New-Object System.Drawing.Size(310,1)
$divider.BackColor = [System.Drawing.Color]::FromArgb(35,49,61)
$left.Controls.Add($divider)

$stackTitle = New-Object System.Windows.Forms.Label
$stackTitle.AutoSize = $true
$stackTitle.Text = "ACTIVE STACK"
$stackTitle.Location = New-Object System.Drawing.Point(20,382)
$stackTitle.Font = New-Font 9 ([System.Drawing.FontStyle]::Bold)
$stackTitle.ForeColor = $ColorMuted
$left.Controls.Add($stackTitle)

$stack = @(
    @{Name="LLM";Value="Gemini 3.5 Flash-Lite"},
    @{Name="ASR";Value="OpenAI Realtime"},
    @{Name="TTS";Value="Sonia / en-GB"},
    @{Name="ENDPOINT";Value="Silero / 700 ms"},
    @{Name="MEMORY";Value="Off (Alpha 2 current)"}
)
$y = 416
foreach ($item in $stack) {
    $name = New-Object System.Windows.Forms.Label
    $name.Location = New-Object System.Drawing.Point(20,$y)
    $name.Size = New-Object System.Drawing.Size(90,22)
    $name.Text = $item.Name
    $name.ForeColor = $ColorMuted
    $name.Font = New-Font 8
    $left.Controls.Add($name)

    $value = New-Object System.Windows.Forms.Label
    $value.Location = New-Object System.Drawing.Point(108,$y)
    $value.Size = New-Object System.Drawing.Size(222,22)
    $value.Text = $item.Value
    $value.ForeColor = $ColorText
    $value.Font = New-Font 9
    $left.Controls.Add($value)
    $y += 30
}

$healthTitle = New-Object System.Windows.Forms.Label
$healthTitle.AutoSize = $true
$healthTitle.Text = "SYSTEM HEALTH"
$healthTitle.Font = New-Font 10 ([System.Drawing.FontStyle]::Bold)
$healthTitle.ForeColor = $ColorText
$healthTitle.Location = New-Object System.Drawing.Point(22,18)
$right.Controls.Add($healthTitle)

function New-HealthLabel {
    param([string]$Text,[int]$X,[int]$Y)
    $label = New-Object System.Windows.Forms.Label
    $label.Size = New-Object System.Drawing.Size(190,34)
    $label.Location = New-Object System.Drawing.Point($X,$Y)
    $label.Text = $Text
    $label.BackColor = $ColorPanelAlt
    $label.ForeColor = $ColorOffline
    $label.TextAlign = "MiddleCenter"
    $label.Font = New-Font 9 ([System.Drawing.FontStyle]::Bold)
    $right.Controls.Add($label)
    $label
}

$serverHealth = New-HealthLabel "SERVER  OFFLINE" 22 52
$robotHealth = New-HealthLabel "ROBOT  DISCONNECTED" 222 52
$asrHealth = New-HealthLabel "ASR  WAITING" 422 52
$personaHealth = New-HealthLabel "PERSONA  CANONICAL V1" 22 94
$personaHealth.ForeColor = $ColorCyan
$modelHealth = New-HealthLabel "MODEL  GEMINI" 222 94
$modelHealth.ForeColor = $ColorCyan
$transportHealth = New-HealthLabel "TRANSPORT  FROZEN" 422 94
$transportHealth.ForeColor = $ColorCyan

$lastTurnTitle = New-Object System.Windows.Forms.Label
$lastTurnTitle.AutoSize = $true
$lastTurnTitle.Text = "LAST HEARD"
$lastTurnTitle.Font = New-Font 9 ([System.Drawing.FontStyle]::Bold)
$lastTurnTitle.ForeColor = $ColorMuted
$lastTurnTitle.Location = New-Object System.Drawing.Point(22,150)
$right.Controls.Add($lastTurnTitle)

$lastTurn = New-Object System.Windows.Forms.Label
$lastTurn.Location = New-Object System.Drawing.Point(22,177)
$lastTurn.Size = New-Object System.Drawing.Size(590,52)
$lastTurn.BackColor = $ColorPanelAlt
$lastTurn.ForeColor = $ColorText
$lastTurn.Padding = New-Object System.Windows.Forms.Padding(10)
$lastTurn.Text = "-"
$lastTurn.Font = New-Font 10
$right.Controls.Add($lastTurn)

$logTitle = New-Object System.Windows.Forms.Label
$logTitle.AutoSize = $true
$logTitle.Text = "LIVE SERVER LOG"
$logTitle.Font = New-Font 9 ([System.Drawing.FontStyle]::Bold)
$logTitle.ForeColor = $ColorMuted
$logTitle.Location = New-Object System.Drawing.Point(22,252)
$right.Controls.Add($logTitle)

$clearButton = New-Object System.Windows.Forms.Button
$clearButton.Text = "CLEAR"
$clearButton.Size = New-Object System.Drawing.Size(74,26)
$clearButton.Location = New-Object System.Drawing.Point(538,244)
$clearButton.FlatStyle = "Flat"
$clearButton.BackColor = $ColorPanelAlt
$clearButton.ForeColor = $ColorMuted
$right.Controls.Add($clearButton)

$logBox = New-Object System.Windows.Forms.RichTextBox
$logBox.Location = New-Object System.Drawing.Point(22,282)
$logBox.Size = New-Object System.Drawing.Size(590,380)
$logBox.Anchor = "Top,Bottom,Left,Right"
$logBox.BackColor = [System.Drawing.Color]::FromArgb(4,7,10)
$logBox.ForeColor = [System.Drawing.Color]::FromArgb(170,208,220)
$logBox.Font = New-Object System.Drawing.Font("Consolas",8.5)
$logBox.ReadOnly = $true
$logBox.WordWrap = $false
$right.Controls.Add($logBox)

$right.add_Resize({
    $available = [Math]::Max(300,$right.ClientSize.Width - 44)
    $lastTurn.Width = $available
    $logBox.Width = $available
    $clearButton.Left = $right.ClientSize.Width - 96
})

function Get-EyeColor {
    switch ($script:EyeState) {
        "booting" { $ColorAmber }
        "online" { $ColorCyan }
        "connected" { $ColorTeal }
        "error" { $ColorRed }
        default { $ColorOffline }
    }
}

$eyePanel.add_Paint({
    param($sender,$e)
    $g = $e.Graphics
    $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
    $eyeColor = Get-EyeColor
    $glowBrush = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(24,$eyeColor.R,$eyeColor.G,$eyeColor.B))
    $irisBrush = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(38,$eyeColor.R,$eyeColor.G,$eyeColor.B))
    $pupilBrush = New-Object System.Drawing.SolidBrush($eyeColor)
    $eyePen = New-Object System.Drawing.Pen($eyeColor,3)
    $ringPen = New-Object System.Drawing.Pen([System.Drawing.Color]::FromArgb(150,$eyeColor.R,$eyeColor.G,$eyeColor.B),2)
    $path = New-Object System.Drawing.Drawing2D.GraphicsPath
    try {
        $g.FillEllipse($glowBrush,84,18,142,142)
        $path.AddBezier(22,90,88,18,222,18,288,90)
        $path.AddBezier(288,90,222,162,88,162,22,90)
        $g.DrawPath($eyePen,$path)
        $g.FillEllipse($irisBrush,108,43,94,94)
        $g.DrawEllipse($ringPen,108,43,94,94)
        $g.DrawEllipse($ringPen,125,60,60,60)
        $g.FillEllipse($pupilBrush,145,80,20,20)
        $g.DrawLine($ringPen,155,33,155,48)
        $g.DrawLine($ringPen,155,132,155,147)
        $g.DrawLine($ringPen,98,90,113,90)
        $g.DrawLine($ringPen,197,90,212,90)
    }
    finally {
        $path.Dispose(); $eyePen.Dispose(); $ringPen.Dispose(); $glowBrush.Dispose(); $irisBrush.Dispose(); $pupilBrush.Dispose()
    }
})

function Set-EyeState {
    param([string]$State)
    $script:EyeState = $State
    $eyePanel.Invalidate()
}

function Append-Log {
    param([string]$Line)
    if ([string]::IsNullOrWhiteSpace($Line)) { return }
    if ($logBox.TextLength -gt 180000) {
        $logBox.Select(0,50000)
        $logBox.SelectedText = ""
    }
    $logBox.AppendText($Line + [Environment]::NewLine)
    $logBox.ScrollToCaret()
}

function Set-OfflineState {
    $script:RobotConnected = $false
    $serverHealth.Text = "SERVER  OFFLINE"; $serverHealth.ForeColor = $ColorOffline
    $robotHealth.Text = "ROBOT  DISCONNECTED"; $robotHealth.ForeColor = $ColorOffline
    $asrHealth.Text = "ASR  WAITING"; $asrHealth.ForeColor = $ColorOffline
    $stateLabel.Text = "SYSTEM OFFLINE"; $stateLabel.ForeColor = $ColorOffline
    Set-EyeState "offline"
}

function Process-ServerLine {
    param([string]$Line)
    Append-Log $Line

    if ($Line -match '=== Kadence 2\.0 Alpha 2 ===') {
        $stateLabel.Text = "INITIALISING"; $stateLabel.ForeColor = $ColorAmber
        $serverHealth.Text = "SERVER  BOOTING"; $serverHealth.ForeColor = $ColorAmber
        Set-EyeState "booting"
    }
    if ($Line -match 'Injected canonical Kadence persona') {
        $personaHealth.Text = "PERSONA  CANONICAL V1"; $personaHealth.ForeColor = $ColorCyan
    }
    if (($Line -match 'Websocket') -and ($Line -match 'ws://')) {
        $serverHealth.Text = "SERVER  ONLINE"; $serverHealth.ForeColor = $ColorCyan
        if (-not $script:RobotConnected) {
            $stateLabel.Text = "SERVER ONLINE"; $stateLabel.ForeColor = $ColorCyan
            Set-EyeState "online"
        }
    }
    if ($Line -match 'K2 ASR LIVE ready:') {
        $asrHealth.Text = "ASR  READY"; $asrHealth.ForeColor = $ColorTeal
    }
    if ($Line -match ' conn - Headers:') {
        $script:RobotConnected = $true
        $robotHealth.Text = "ROBOT  CONNECTED"; $robotHealth.ForeColor = $ColorTeal
        $stateLabel.Text = "KADENCE ONLINE"; $stateLabel.ForeColor = $ColorTeal
        Set-EyeState "connected"
    }
    if ($Line -match 'K2 ASR LIVE -> chat:\s*(.+)$') {
        $lastTurn.Text = $Matches[1].Trim()
    }
    if ($Line -match 'GeminiLLM') {
        $modelHealth.Text = "MODEL  GEMINI"; $modelHealth.ForeColor = $ColorCyan
    }
    if (($Line -match 'Traceback') -or ($Line -match 'ERROR')) {
        if (-not $script:StopRequested) {
            $stateLabel.Text = "ATTENTION REQUIRED"; $stateLabel.ForeColor = $ColorRed
            Set-EyeState "error"
        }
    }
}

function Close-BackendLog {
    if ($null -ne $script:LogReader) { $script:LogReader.Dispose(); $script:LogReader = $null }
    if ($null -ne $script:LogStream) { $script:LogStream.Dispose(); $script:LogStream = $null }
}

function Start-Backend {
    if (($null -ne $script:BackendProcess) -and (-not $script:BackendProcess.HasExited)) { return }

    $script:StopRequested = $false
    $script:ExitReported = $false
    $script:RobotConnected = $false
    $lastTurn.Text = "-"
    $stateLabel.Text = "INITIALISING"; $stateLabel.ForeColor = $ColorAmber
    $serverHealth.Text = "SERVER  BOOTING"; $serverHealth.ForeColor = $ColorAmber
    $robotHealth.Text = "ROBOT  DISCONNECTED"; $robotHealth.ForeColor = $ColorOffline
    $asrHealth.Text = "ASR  WAITING"; $asrHealth.ForeColor = $ColorOffline
    Set-EyeState "booting"
    $startButton.Enabled = $false; $startButton.ForeColor = $ColorOffline
    $stopButton.Enabled = $true; $stopButton.ForeColor = $ColorRed; $stopButton.FlatAppearance.BorderColor = $ColorRed
    Append-Log "[KADENCE UI] Starting Alpha 2 backend..."

    try {
        Close-BackendLog
        $token = [guid]::NewGuid().ToString("N")
        $script:BackendLogPath = Join-Path $env:TEMP ("kadence-alpha2-{0}.log" -f $token)
        $script:BackendCmdPath = Join-Path $env:TEMP ("kadence-alpha2-{0}.cmd" -f $token)
        [System.IO.File]::WriteAllText($script:BackendLogPath,"",[System.Text.Encoding]::UTF8)

        $cmdText = "@echo off`r`n`"$WindowsPowerShell`" -NoLogo -NoProfile -ExecutionPolicy Bypass -File `"$StartScript`" > `"$($script:BackendLogPath)`" 2>&1`r`nexit /b %errorlevel%`r`n"
        [System.IO.File]::WriteAllText($script:BackendCmdPath,$cmdText,[System.Text.Encoding]::ASCII)

        $startInfo = New-Object System.Diagnostics.ProcessStartInfo
        $startInfo.FileName = $CmdExe
        $startInfo.Arguments = "/d /c `"`"$($script:BackendCmdPath)`"`""
        $startInfo.WorkingDirectory = $BackendRoot
        $startInfo.UseShellExecute = $false
        $startInfo.CreateNoWindow = $true

        $process = New-Object System.Diagnostics.Process
        $process.StartInfo = $startInfo
        if (-not $process.Start()) { throw "Windows failed to launch the backend wrapper." }
        $script:BackendProcess = $process

        $script:LogStream = New-Object System.IO.FileStream($script:BackendLogPath,[System.IO.FileMode]::Open,[System.IO.FileAccess]::Read,[System.IO.FileShare]::ReadWrite)
        $script:LogReader = New-Object System.IO.StreamReader($script:LogStream,[System.Text.Encoding]::Default,$true,4096,$true)
        Append-Log ("[KADENCE UI] Backend wrapper PID {0}" -f $process.Id)
    }
    catch {
        Append-Log ("[KADENCE UI] START FAILED: " + $_.Exception.Message)
        $serverHealth.Text = "SERVER  FAILED"; $serverHealth.ForeColor = $ColorRed
        $stateLabel.Text = "START FAILED"; $stateLabel.ForeColor = $ColorRed
        Set-EyeState "error"
        $startButton.Enabled = $true; $startButton.ForeColor = $ColorCyan
        $stopButton.Enabled = $false; $stopButton.ForeColor = $ColorOffline; $stopButton.FlatAppearance.BorderColor = $ColorOffline
        $script:BackendProcess = $null
        Close-BackendLog
    }
}

function Stop-Backend {
    param([bool]$Silent = $false)
    if (($null -eq $script:BackendProcess) -or $script:BackendProcess.HasExited) {
        Set-OfflineState
        return
    }
    $script:StopRequested = $true
    $stateLabel.Text = "SHUTTING DOWN"; $stateLabel.ForeColor = $ColorAmber
    $serverHealth.Text = "SERVER  STOPPING"; $serverHealth.ForeColor = $ColorAmber
    Set-EyeState "booting"
    if (-not $Silent) { Append-Log "[KADENCE UI] Stopping backend process tree..." }
    try {
        $pidToStop = $script:BackendProcess.Id
        $taskkill = Start-Process -FilePath "taskkill.exe" -ArgumentList "/PID $pidToStop /T /F" -WindowStyle Hidden -Wait -PassThru
        if (($taskkill.ExitCode -ne 0) -and (-not $script:BackendProcess.HasExited)) { throw "taskkill exited with code $($taskkill.ExitCode)." }
    }
    catch {
        Append-Log ("[KADENCE UI] STOP WARNING: " + $_.Exception.Message)
    }
}

$startButton.add_Click({ Start-Backend })
$stopButton.add_Click({ Stop-Backend })
$clearButton.add_Click({ $logBox.Clear() })

$timer = New-Object System.Windows.Forms.Timer
$timer.Interval = 150
$timer.add_Tick({
    try {
        if ($null -ne $script:LogReader) {
            while (-not $script:LogReader.EndOfStream) {
                $line = $script:LogReader.ReadLine()
                if ($null -ne $line) { Process-ServerLine $line }
            }
        }

        if (($null -ne $script:BackendProcess) -and $script:BackendProcess.HasExited -and (-not $script:ExitReported)) {
            $script:ExitReported = $true
            $exitCode = $script:BackendProcess.ExitCode
            if ($script:StopRequested) {
                Append-Log "[KADENCE UI] Backend stopped."
                Set-OfflineState
            }
            else {
                Append-Log ("[KADENCE UI] Backend exited unexpectedly with code {0}." -f $exitCode)
                $serverHealth.Text = "SERVER  EXITED"; $serverHealth.ForeColor = $ColorRed
                $stateLabel.Text = "BACKEND EXITED"; $stateLabel.ForeColor = $ColorRed
                Set-EyeState "error"
            }
            $startButton.Enabled = $true; $startButton.ForeColor = $ColorCyan
            $stopButton.Enabled = $false; $stopButton.ForeColor = $ColorOffline; $stopButton.FlatAppearance.BorderColor = $ColorOffline
        }
    }
    catch {
        Append-Log ("[KADENCE UI] MONITOR ERROR: " + $_.Exception.Message)
        $stateLabel.Text = "MONITOR ERROR"; $stateLabel.ForeColor = $ColorRed
        Set-EyeState "error"
    }
})
$timer.Start()

$form.add_FormClosing({
    param($sender,$e)
    if (($null -ne $script:BackendProcess) -and (-not $script:BackendProcess.HasExited)) {
        $answer = [System.Windows.Forms.MessageBox]::Show("The Kadence backend is still running. Stop it and exit?","Kadence Control Surface",[System.Windows.Forms.MessageBoxButtons]::YesNo,[System.Windows.Forms.MessageBoxIcon]::Question)
        if ($answer -ne [System.Windows.Forms.DialogResult]::Yes) { $e.Cancel = $true; return }
        Stop-Backend -Silent $true
    }
})

Append-Log "[KADENCE UI] Control Surface ready."
Append-Log "[KADENCE UI] Milestone 2 foundation: server boot / stop / health / live log."
Append-Log "[KADENCE UI] Backend monitoring uses file-tail isolation; no async PowerShell event callbacks."

try {
    [void]$form.ShowDialog()
}
finally {
    $timer.Stop()
    Close-BackendLog
    if ($script:BackendLogPath -and (Test-Path $script:BackendLogPath)) { Remove-Item $script:BackendLogPath -Force -ErrorAction SilentlyContinue }
    if ($script:BackendCmdPath -and (Test-Path $script:BackendCmdPath)) { Remove-Item $script:BackendCmdPath -Force -ErrorAction SilentlyContinue }
}
