param(
    [string]$RuntimeRoot = (Join-Path $PSScriptRoot ".runtime")
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$RepoDir = Join-Path $RuntimeRoot "xiaozhi-esp32-server"
$ServerDir = Join-Path $RepoDir "main\xiaozhi-server"
$AppPath = Join-Path $ServerDir "app.py"
$ConnectionPath = Join-Path $ServerDir "core\connection.py"
$BehaviorTarget = Join-Path $ServerDir "core\kadence_behavior.py"
$Utf8NoBom = [System.Text.UTF8Encoding]::new($false)

foreach ($RequiredPath in @($AppPath,$ConnectionPath)) {
    if (-not (Test-Path $RequiredPath)) {
        throw "Kadence M7 rollback required path was not found: $RequiredPath"
    }
}

# Remove only Project-owned M7 additions from app.py.
$AppText = [System.IO.File]::ReadAllText($AppPath,$Utf8NoBom).Replace("`r`n","`n")
$OriginalAppText = $AppText
$AppImport = @'
from core.kadence_behavior import (
    start_kadence_behavior_server,
    stop_kadence_behavior_server,
)
'@.Replace("`r`n","`n")
$AppText = $AppText.Replace($AppImport,"")
$AppText = $AppText.Replace("    behavior_server = start_kadence_behavior_server(logger=logger)`n","")
$AppText = $AppText.Replace("        stop_kadence_behavior_server(behavior_server)`n","")

if ($AppText.Contains("kadence_behavior") -or
    $AppText.Contains("start_kadence_behavior_server") -or
    $AppText.Contains("stop_kadence_behavior_server")) {
    throw "Kadence M7 rollback app verification failed; behaviour-control markers remain."
}
if ($AppText -ne $OriginalAppText) {
    [System.IO.File]::WriteAllText($AppPath,$AppText,$Utf8NoBom)
    Write-Host "Removed Kadence M7 loopback behaviour control from local runtime."
} else {
    Write-Host "Kadence M7 app control already absent."
}

# Restore connection.py to the proven M6 root-turn shape while leaving M4/M5/M6
# history/tool wiring untouched.
$ConnText = [System.IO.File]::ReadAllText($ConnectionPath,$Utf8NoBom).Replace("`r`n","`n")
$OriginalConnText = $ConnText
$ConnText = $ConnText.Replace(
    "from core.kadence_behavior import render_kadence_behavior_prompt, get_kadence_behavior_snapshot`n",
    ""
)
$ConnText = $ConnText.Replace(
    "from core.kadence_behavior import render_kadence_behavior_prompt`n",
    ""
)

$M6Root = @'
        if depth == 0:
            self._kadence_tool_root_query = query
            current_sentence_id = str(uuid.uuid4().hex)
'@.Replace("`r`n","`n")
$M7RootV1 = @'
        if depth == 0:
            if self.prompt:
                self.dialogue.update_system_message(
                    render_kadence_behavior_prompt(self.prompt)
                )
            self._kadence_tool_root_query = query
            current_sentence_id = str(uuid.uuid4().hex)
'@.Replace("`r`n","`n")
$M7RootV2 = @'
        if depth == 0:
            kadence_behavior_state = get_kadence_behavior_snapshot()
            if self.prompt:
                self.dialogue.update_system_message(
                    render_kadence_behavior_prompt(self.prompt)
                )
            self.logger.bind(tag=TAG).info(
                f"KADENCE BEHAVIOR: turn mode={kadence_behavior_state['mode']} chars={kadence_behavior_state['chars']}"
            )
            self._kadence_tool_root_query = query
            current_sentence_id = str(uuid.uuid4().hex)
'@.Replace("`r`n","`n")

if ($ConnText.Contains($M7RootV2)) {
    $ConnText = $ConnText.Replace($M7RootV2,$M6Root)
    Write-Host "Removed Kadence M7 traced prompt overlay from local runtime."
} elseif ($ConnText.Contains($M7RootV1)) {
    $ConnText = $ConnText.Replace($M7RootV1,$M6Root)
    Write-Host "Removed Kadence M7 prompt overlay from local runtime."
} elseif ($ConnText.Contains($M6Root)) {
    Write-Host "Kadence M7 prompt overlay already absent."
} else {
    throw "Kadence M7 rollback root-turn guard failed; refusing to guess at connection.py."
}

foreach ($Forbidden in @(
    "render_kadence_behavior_prompt",
    "get_kadence_behavior_snapshot",
    "KADENCE BEHAVIOR: turn mode="
)) {
    if ($ConnText.Contains($Forbidden)) {
        throw "Kadence M7 rollback connection verification failed; marker remains: $Forbidden"
    }
}
if (-not $ConnText.Contains($M6Root)) {
    throw "Kadence M7 rollback failed to restore proven M6 root-turn capture."
}
if ($ConnText -ne $OriginalConnText) {
    [System.IO.File]::WriteAllText($ConnectionPath,$ConnText,$Utf8NoBom)
}

if (Test-Path $BehaviorTarget) {
    Remove-Item $BehaviorTarget -Force
    Write-Host "Removed Kadence M7 runtime behaviour helper."
}

Write-Host "Kadence runtime restored to M6 behaviour state; CUSTOM overlay inactive."
