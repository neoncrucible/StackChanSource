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
$ColorBorder = [System.Drawing.Color]::FromArgb(35,49,61)

function New-Font {
    param([float]$Size, [System.Drawing.FontStyle]$Style = [System.Drawing.FontStyle]::Regular, [string]$Family = "Segoe UI")
    New-Object System.Drawing.Font($Family, $Size, $Style)
}

function New-PanelLabel {
    param([string]$Text)
    $label = New-Object System.Windows.Forms.Label
    $label.Dock = "Fill"
    $label.Text = $Text
    $label.TextAlign = "MiddleCenter"
    $label.BackColor = $ColorPanelAlt
    $label.ForeColor = $ColorOffline
    $label.Font = New-Font 9 ([System.Drawing.FontStyle]::Bold)
    $label.Margin = New-Object System.Windows.Forms.Padding(0)
    return $label
}

$form = New-Object System.Windows.Forms.Form
$form.Text = "Kadence 2.0 - Control Surface"
$form.StartPosition = "CenterScreen"
$form.Size = New-Object System.Drawing.Size(1220,820)
$form.MinimumSize = New-Object System.Drawing.Size(1050,720)
$form.BackColor = $ColorBg
$form.ForeColor = $ColorText
$form.Font = New-Font 10

$outer = New-Object System.Windows.Forms.TableLayoutPanel
$outer.Dock = "Fill"
$outer.BackColor = $ColorBg
$outer.ColumnCount = 1
$outer.RowCount = 2
$outer.RowStyles.Add((New-Object System.Windows.Forms.RowStyle([System.Windows.Forms.SizeType]::Absolute,78))) | Out-Null
$outer.RowStyles.Add((New-Object System.Windows.Forms.RowStyle([System.Windows.Forms.SizeType]::Percent,100))) | Out-Null
$form.Controls.Add($outer)

$header = New-Object System.Windows.Forms.Panel
$header.Dock = "Fill"
$header.BackColor = $ColorBg
$outer.Controls.Add($header,0,0)

$title = New-Object System.Windows.Forms.Label
$title.AutoSize = $true
$title.Text = "PROJECT KADENCE"
$title.Font = New-Font 19 ([System.Drawing.FontStyle]::Bold)
$title.ForeColor = $ColorText
$title.Location = New-Object System.Drawing.Point(24,14)
$header.Controls.Add($title)

$subtitle = New-Object System.Windows.Forms.Label
$subtitle.AutoSize = $true
$subtitle.Text = "ALPHA 2  /  CONTROL SURFACE"
$subtitle.Font = New-Font 9 ([System.Drawing.FontStyle]::Bold)
$subtitle.ForeColor = $ColorCyan
$subtitle.Location = New-Object System.Drawing.Point(27,49)
$header.Controls.Add($subtitle)

$body = New-Object System.Windows.Forms.TableLayoutPanel
$body.Dock = "Fill"
$body.BackColor = $ColorBg
$body.Padding = New-Object System.Windows.Forms.Padding(20,8,20,20)
$body.ColumnCount = 2
$body.RowCount = 1
$body.ColumnStyles.Add((New-Object System.Windows.Forms.ColumnStyle([System.Windows.Forms.SizeType]::Absolute,360))) | Out-Null
$body.ColumnStyles.Add((New-Object System.Windows.Forms.ColumnStyle([System.Windows.Forms.SizeType]::Percent,100))) | Out-Null
$outer.Controls.Add($body,0,1)

$left = New-Object System.Windows.Forms.Panel
$left.Dock = "Fill"
$left.BackColor = $ColorPanel
$left.Margin = New-Object System.Windows.Forms.Padding(0,0,12,0)
$body.Controls.Add($left,0,0)

$right = New-Object System.Windows.Forms.Panel
$right.Dock = "Fill"
$right.BackColor = $ColorPanel
$right.Margin = New-Object System.Windows.Forms.Padding(0)
$body.Controls.Add($right,1,0)

$eyePanel = New-Object System.Windows.Forms.Panel
$eyePanel.Location = New-Object System.Drawing.Point(24,18)
$eyePanel.Size = New-Object System.Drawing.Size(312,178)
$eyePanel.BackColor = $ColorPanel
$left.Controls.Add($eyePanel)

$stateLabel = New-Object System.Windows.Forms.Label
$stateLabel.Size = New-Object System.Drawing.Size(312,34)
$stateLabel.Location = New-Object System.Drawing.Point(24,204)
$stateLabel.TextAlign = "MiddleCenter"
$stateLabel.Font = New-Font 15 ([System.Drawing.FontStyle]::Bold)
$stateLabel.Text = "SYSTEM OFFLINE"
$stateLabel.ForeColor = $ColorOffline
$left.Controls.Add($stateLabel)

$modeLabel = New-Object System.Windows.Forms.Label
$modeLabel.Size = New-Object System.Drawing.Size(312,24)
$modeLabel.Location = New-Object System.Drawing.Point(24,238)
$modeLabel.TextAlign = "MiddleCenter"
$modeLabel.Font = New-Font 9
$modeLabel.ForeColor = $ColorMuted
$modeLabel.Text = "Canonical identity / Gemini Flash-Lite"
$left.Controls.Add($modeLabel)

$buttonRow = New-Object System.Windows.Forms.TableLayoutPanel
$buttonRow.Location = New-Object System.Drawing.Point(24,282)
$buttonRow.Size = New-Object System.Drawing.Size(312,46)
$buttonRow.ColumnCount = 2
$buttonRow.RowCount = 1
$buttonRow.ColumnStyles.Add((New-Object System.Windows.Forms.ColumnStyle([System.Windows.Forms.SizeType]::Percent,50))) | Out-Null
$buttonRow.ColumnStyles.Add((New-Object System.Windows.Forms.ColumnStyle([System.Windows.Forms.SizeType]::Percent,50))) | Out-Null
$left.Controls.Add($buttonRow)

$startButton = New-Object System.Windows.Forms.Button
$startButton.Text = "START SERVER"
$startButton.Dock = "Fill"
$startButton.Margin = New-Object System.Windows.Forms.Padding(0,0,6,0)
$startButton.FlatStyle = "Flat"
$startButton.FlatAppearance.BorderColor = $ColorCyan
$startButton.FlatAppearance.BorderSize = 1
$startButton.BackColor = $ColorPanelAlt
$startButton.ForeColor = $ColorCyan
$startButton.Font = New-Font 10 ([System.Drawing.FontStyle]::Bold)
$buttonRow.Controls.Add($startButton,0,0)

$stopButton = New-Object System.Windows.Forms.Button
$stopButton.Text = "STOP SERVER"
$stopButton.Dock = "Fill"
$stopButton.Margin = New-Object System.Windows.Forms.Padding(6,0,0,0)
$stopButton.FlatStyle = "Flat"
$stopButton.FlatAppearance.BorderColor = $ColorOffline
$stopButton.FlatAppearance.BorderSize = 1
$stopButton.BackColor = $ColorPanelAlt
$stopButton.ForeColor = $ColorOffline
$stopButton.Font = New-Font 10 ([System.Drawing.FontStyle]::Bold)
$stopButton.Enabled = $false
$buttonRow.Controls.Add($stopButton,1,0)

$divider = New-Object System.Windows.Forms.Label
$divider.Location = New-Object System.Drawing.Point(24,354)
$divider.Size = New-Object System.Drawing.Size(312,1)
$divider.BackColor = $ColorBorder
$left.Controls.Add($divider)

$stackTitle = New-Object System.Windows.Forms.Label
$stackTitle.AutoSize = $true
$stackTitle.Text = "ACTIVE STACK"
$stackTitle.Location = New-Object System.Drawing.Point(24,373)
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
$y = 407
foreach ($item in $stack) {
    $name = New-Object System.Windows.Forms.Label
    $name.Location = New-Object System.Drawing.Point(24,$y)
    $name.Size = New-Object System.Drawing.Size(92,22)
    $name.Text = $item.Name
    $name.ForeColor = $ColorMuted
    $name.Font = New-Font 8
    $left.Controls.Add($name)

    $value = New-Object System.Windows.Forms.Label
    $value.Location = New-Object System.Drawing.Point(118,$y)
    $value.Size = New-Object System.Drawing.Size(218,22)
    $value.Text = $item.Value
    $value.ForeColor = $ColorText
    $value.Font = New-Font 9
    $left.Controls.Add($value)
    $y += 31
}

$healthTitle = New-Object System.Windows.Forms.Label
$healthTitle.AutoSize = $true
$healthTitle.Text = "SYSTEM HEALTH"
$healthTitle.Font = New-Font 10 ([System.Drawing.FontStyle]::Bold)
$healthTitle.ForeColor = $ColorText
$healthTitle.Location = New-Object System.Drawing.Point(24,20)
$right.Controls.Add($healthTitle)

$healthGrid = New-Object System.Windows.Forms.TableLayoutPanel
$healthGrid.Location = New-Object System.Drawing.Point(24,52)
$healthGrid.Size = New-Object System.Drawing.Size(720,78)
$healthGrid.Anchor = "Top,Left,Right"
$healthGrid.ColumnCount = 3
$healthGrid.RowCount = 2
for ($i=0; $i -lt 3; $i++) {
    $healthGrid.ColumnStyles.Add((New-Object System.Windows.Forms.ColumnStyle([System.Windows.Forms.SizeType]::Percent,33.333))) | Out-Null
}
$healthGrid.RowStyles.Add((New-Object System.Windows.Forms.RowStyle([System.Windows.Forms.SizeType]::Percent,50))) | Out-Null
$healthGrid.RowStyles.Add((New-Object System.Windows.Forms.RowStyle([System.Windows.Forms.SizeType]::Percent,50))) | Out-Null
$healthGrid.Padding = New-Object System.Windows.Forms.Padding(0)
$right.Controls.Add($healthGrid)

$serverHealth = New-PanelLabel "SERVER  OFFLINE"
$robotHealth = New-PanelLabel "ROBOT  DISCONNECTED"
$asrHealth = New-PanelLabel "ASR  WAITING"
$personaHealth = New-PanelLabel "PERSONA  CANONICAL V1"
$modelHealth = New-PanelLabel "MODEL  GEMINI"
$transportHealth = New-PanelLabel "TRANSPORT  FROZEN"
$personaHealth.ForeColor = $ColorCyan
$modelHealth.ForeColor = $ColorCyan
$transportHealth.ForeColor = $ColorCyan

$serverHealth.Margin = New-Object System.Windows.Forms.Padding(0,0,6,6)
$robotHealth.Margin = New-Object System.Windows.Forms.Padding(3,0,3,6)
$asrHealth.Margin = New-Object System.Windows.Forms.Padding(6,0,0,6)
$personaHealth.Margin = New-Object System.Windows.Forms.Padding(0,3,6,0)
$modelHealth.Margin = New-Object System.Windows.Forms.Padding(3,3,3,0)
$transportHealth.Margin = New-Object System.Windows.Forms.Padding(6,3,0,0)

$healthGrid.Controls.Add($serverHealth,0,0)
$healthGrid.Controls.Add($robotHealth,1,0)
$healthGrid.Controls.Add($asrHealth,2,0)
$healthGrid.Controls.Add($personaHealth,0,1)
$healthGrid.Controls.Add($modelHealth,1,1)
$healthGrid.Controls.Add($transportHealth,2,1)

$lastTurnTitle = New-Object System.Windows.Forms.Label
$lastTurnTitle.AutoSize = $true
$lastTurnTitle.Text = "LAST HEARD"
$lastTurnTitle.Font = New-Font 9 ([System.Drawing.FontStyle]::Bold)
$lastTurnTitle.ForeColor = $ColorMuted
$lastTurnTitle.Location = New-Object System.Drawing.Point(24,154)
$right.Controls.Add($lastTurnTitle)

$lastTurn = New-Object System.Windows.Forms.Label
$lastTurn.Location = New-Object System.Drawing.Point(24,181)
$lastTurn.Size = New-Object System.Drawing.Size(720,54)
$lastTurn.Anchor = "Top,Left,Right"
$lastTurn.BackColor = $ColorPanelAlt
$lastTurn.ForeColor = $ColorText
$lastTurn.Padding = New-Object System.Windows.Forms.Padding(12)
$lastTurn.Text = "-"
$lastTurn.Font = New-Font 10
$right.Controls.Add($lastTurn)

$logTitle = New-Object System.Windows.Forms.Label
$logTitle.AutoSize = $true
$logTitle.Text = "LIVE SERVER LOG"
$logTitle.Font = New-Font 9 ([System.Drawing.FontStyle]::Bold)
$logTitle.ForeColor = $ColorMuted
$logTitle.Location = New-Object System.Drawing.Point(24,260)
$right.Controls.Add($logTitle)

$clearButton = New-Object System.Windows.Forms.Button
$clearButton.Text = "CLEAR"
$clearButton.Size = New-Object System.Drawing.Size(78,26)
$clearButton.Location = New-Object System.Drawing.Point(666,251)
$clearButton.Anchor = "Top,Right"
$clearButton.FlatStyle = "Flat"
$clearButton.FlatAppearance.BorderColor = $ColorBorder
$clearButton.BackColor = $ColorPanelAlt
$clearButton.ForeColor = $ColorMuted
$clearButton.Font = New-Font 8 ([System.Drawing.FontStyle]::Bold)
$right.Controls.Add($clearButton)

$logBox = New-Object System.Windows.Forms.RichTextBox
$logBox.Location = New-Object System.Drawing.Point(24,290)
$logBox.Size = New-Object System.Drawing.Size(720,390)
$logBox.Anchor = "Top,Bottom,Left,Right"
$logBox.BackColor = [System.Drawing.Color]::FromArgb(4,7,10)
$logBox.ForeColor = [System.Drawing.Color]::FromArgb(170,208,220)
$logBox.BorderStyle = "FixedSingle"
$logBox.Font = New-Font 8.5 ([System.Drawing.FontStyle]::Regular) "Consolas"
$logBox.ReadOnly = $true
$logBox.WordWrap = $false
$logBox.HideSelection = $true
$right.Controls.Add($logBox)

$right.add_Resize({
    $width = [Math]::Max(480,$right.ClientSize.Width - 48)
    $healthGrid.Width = $width
    $lastTurn.Width = $width
    $logBox.Width = $width
    $clearButton.Left = $right.ClientSize.Width - 102
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
        $g.FillEllipse($glowBrush,85,8,142,142)
        $path.AddBezier(22,79,88,7,224,7,290,79)
        $path.AddBezier(290,79,224,151,88,151,22,79)
        $g.DrawPath($eyePen,$path)
        $g.FillEllipse($irisBrush,109,32,94,94)
        $g.DrawEllipse($ringPen,109,32,94,94)
        $g.DrawEllipse($ringPen,126,49,60,60)
        $g.FillEllipse($pupilBrush,146,69,20,20)
        $g.DrawLine($ringPen,156,22,156,37)
        $g.DrawLine($ringPen,156,121,156,136)
        $g.DrawLine($ringPen,99,79,114,79)
        $g.DrawLine($ringPen,198,79,213,79)
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
    $logBox.SelectionStart = $logBox.TextLength
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

function Get-PortConflicts {
    $items = New-Object System.Collections.Generic.List[object]

    $udp = Get-NetUDPEndpoint -LocalPort 45872 -ErrorAction SilentlyContinue
    foreach ($entry in @($udp)) {
        if ($null -ne $entry) {
            $items.Add([pscustomobject]@{Protocol="UDP";Port=45872;Pid=$entry.OwningProcess})
        }
    }

    foreach ($port in @(8000,8003)) {
        $tcp = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue
        foreach ($entry in @($tcp)) {
            if ($null -ne $entry) {
                $items.Add([pscustomobject]@{Protocol="TCP";Port=$port;Pid=$entry.OwningProcess})
            }
        }
    }

    return $items
}

function Describe-Process {
    param([int]$Pid)
    try {
        $p = Get-CimInstance Win32_Process -Filter ("ProcessId={0}" -f $Pid) -ErrorAction Stop
        if ($null -ne $p) {
            $cmd = [string]$p.CommandLine
            if ($cmd.Length -gt 160) { $cmd = $cmd.Substring(0,157) + "..." }
            return ("PID {0} / {1} / {2}" -f $Pid,$p.Name,$cmd)
        }
    }
    catch {}
    return ("PID {0}" -f $Pid)
}

function Process-ServerLine {
    param([string]$Line)
    Append-Log $Line

    if ($Line -match '=== Kadence 2\.0 Alpha 2 ===') {
        $stateLabel.Text = "INITIALISING"; $stateLabel.ForeColor = $ColorAmber
        $serverHealth.Text = "SERVER  BOOTING"; $serverHealth.ForeColor = $ColorAmber
        Set-EyeState "booting"
    }
    if (($Line -match 'canonical Kadence persona') -or ($Line -match 'Canonical Kadence persona already matches')) {
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
    if (($Line -match 'Traceback') -or ($Line -match 'ERROR') -or ($Line -match 'Errno 10048')) {
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

    $conflicts = @(Get-PortConflicts)
    if ($conflicts.Count -gt 0) {
        Append-Log "[KADENCE UI] START BLOCKED: required local port(s) already in use."
        foreach ($c in $conflicts) {
            Append-Log ("[KADENCE UI] {0} {1} busy - {2}" -f $c.Protocol,$c.Port,(Describe-Process -Pid $c.Pid))
        }
        Append-Log "[KADENCE UI] Stop the stale process deliberately, then try START SERVER again."
        $stateLabel.Text = "PORT CONFLICT"; $stateLabel.ForeColor = $ColorRed
        $serverHealth.Text = "SERVER  BLOCKED"; $serverHealth.ForeColor = $ColorRed
        Set-EyeState "error"
        return
    }

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
        [System.IO.File]::WriteAllText($script:BackendLogPath,"",[System.Text.UTF8Encoding]::new($false))

        $cmdText = @"
@echo off
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
"$WindowsPowerShell" -NoLogo -NoProfile -ExecutionPolicy Bypass -Command "[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new(`$false); `$OutputEncoding=[System.Text.UTF8Encoding]::new(`$false); & '$StartScript'" > "$($script:BackendLogPath)" 2>&1
exit /b %errorlevel%
"@
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
        $script:LogReader = New-Object System.IO.StreamReader($script:LogStream,[System.Text.Encoding]::UTF8,$true,4096,$true)
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
        $startButton.Enabled = $true; $startButton.ForeColor = $ColorCyan
        $stopButton.Enabled = $false; $stopButton.ForeColor = $ColorOffline; $stopButton.FlatAppearance.BorderColor = $ColorOffline
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
Append-Log "[KADENCE UI] Preflight protects UDP 45872 and TCP 8000/8003; backend logs forced to UTF-8."

try {
    [void]$form.ShowDialog()
}
finally {
    $timer.Stop()
    Close-BackendLog
    if ($script:BackendLogPath -and (Test-Path $script:BackendLogPath)) { Remove-Item $script:BackendLogPath -Force -ErrorAction SilentlyContinue }
    if ($script:BackendCmdPath -and (Test-Path $script:BackendCmdPath)) { Remove-Item $script:BackendCmdPath -Force -ErrorAction SilentlyContinue }
}
