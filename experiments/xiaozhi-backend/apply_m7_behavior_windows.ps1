param(
    [string]$RuntimeRoot = (Join-Path $PSScriptRoot ".runtime")
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$RepoDir = Join-Path $RuntimeRoot "xiaozhi-esp32-server"
$ServerDir = Join-Path $RepoDir "main\xiaozhi-server"
$AppPath = Join-Path $ServerDir "app.py"
$ConnectionPath = Join-Path $ServerDir "core\connection.py"
$BehaviorSource = Join-Path $PSScriptRoot "kadence_behavior.py"
$BehaviorTarget = Join-Path $ServerDir "core\kadence_behavior.py"
$Utf8NoBom = [System.Text.UTF8Encoding]::new($false)

foreach ($RequiredPath in @(
    $RepoDir,
    $AppPath,
    $ConnectionPath,
    $BehaviorSource
)) {
    if (-not (Test-Path $RequiredPath)) {
        throw "Kadence M7 required path was not found: $RequiredPath"
    }
}

$SourceText = [System.IO.File]::ReadAllText($BehaviorSource, $Utf8NoBom)
$TargetText = if (Test-Path $BehaviorTarget) {
    [System.IO.File]::ReadAllText($BehaviorTarget, $Utf8NoBom)
} else {
    ""
}
if ($SourceText -ne $TargetText) {
    [System.IO.File]::WriteAllText($BehaviorTarget, $SourceText, $Utf8NoBom)
    Write-Host "Installed Kadence M7 volatile behaviour helper into local runtime."
} else {
    Write-Host "Kadence M7 volatile behaviour helper already installed."
}

# ---------------------------------------------------------------------------
# app.py: process-owned loopback control plane. It binds only 127.0.0.1 and the
# helper state begins empty for every backend process, so a server restart is a
# hard reset to DEFAULT without writing any behaviour text to disk.
# ---------------------------------------------------------------------------
$AppText = [System.IO.File]::ReadAllText($AppPath, $Utf8NoBom).Replace("`r`n", "`n")
$AppChanged = $false

$AppImportOriginal = "from core.utils.gc_manager import get_gc_manager`n"
$AppImportPatched = @'
from core.utils.gc_manager import get_gc_manager
from core.kadence_behavior import (
    start_kadence_behavior_server,
    stop_kadence_behavior_server,
)
'@.Replace("`r`n", "`n")
if ($AppText.Contains($AppImportPatched)) {
    Write-Host "Kadence M7 app control import: already applied."
}
elseif ($AppText.Contains($AppImportOriginal)) {
    $AppText = $AppText.Replace($AppImportOriginal, $AppImportPatched)
    $AppChanged = $true
    Write-Host "Applied Kadence M7 app control import."
}
else {
    throw "Kadence M7 app import guard failed; refusing to modify runtime."
}

$AppStartOriginal = @'
async def main():
    check_ffmpeg_installed()
    config = await load_config()

'@.Replace("`r`n", "`n")
$AppStartPatched = @'
async def main():
    check_ffmpeg_installed()
    config = await load_config()
    behavior_server = start_kadence_behavior_server(logger=logger)

'@.Replace("`r`n", "`n")
if ($AppText.Contains($AppStartPatched)) {
    Write-Host "Kadence M7 loopback control startup: already applied."
}
elseif ($AppText.Contains($AppStartOriginal)) {
    $AppText = $AppText.Replace($AppStartOriginal, $AppStartPatched)
    $AppChanged = $true
    Write-Host "Applied Kadence M7 loopback control startup."
}
else {
    throw "Kadence M7 app startup guard failed; refusing to modify runtime."
}

$AppStopMarker = "        stop_kadence_behavior_server(behavior_server)`n"
if ($AppText.Contains($AppStopMarker)) {
    Write-Host "Kadence M7 loopback control shutdown: already applied."
}
else {
    $AppStopMatches = [regex]::Matches(
        $AppText,
        '(?m)^        await gc_manager\.stop\(\)\s*$'
    )
    if ($AppStopMatches.Count -ne 1) {
        throw "Kadence M7 app shutdown guard failed: expected exactly one gc_manager.stop() site, found $($AppStopMatches.Count)."
    }

    $StopLine = $AppStopMatches[0].Value
    $StopReplacement = "        stop_kadence_behavior_server(behavior_server)`n        await gc_manager.stop()"
    $AppText = $AppText.Replace($StopLine, $StopReplacement)
    $AppChanged = $true
    Write-Host "Applied Kadence M7 loopback control shutdown."
}

if (-not $AppText.Contains("start_kadence_behavior_server") -or
    -not $AppText.Contains("stop_kadence_behavior_server(behavior_server)")) {
    throw "Kadence M7 app post-patch verification failed."
}
if ($AppChanged) {
    [System.IO.File]::WriteAllText($AppPath, $AppText, $Utf8NoBom)
    Write-Host "Kadence M7 process-owned behaviour control installed."
}

# ---------------------------------------------------------------------------
# connection.py: compose the current process overlay onto the already-enhanced
# canonical prompt only at the start of a top-level user turn. self.prompt stays
# canonical, so DEFAULT can restore it cleanly and recursive tool turns retain a
# consistent prompt for the turn already in progress.
# ---------------------------------------------------------------------------
$ConnText = [System.IO.File]::ReadAllText($ConnectionPath, $Utf8NoBom).Replace("`r`n", "`n")
$ConnChanged = $false

$LegacyFusedImport = "from core.kadence_behavior import render_kadence_behavior_promptfrom plugins_func.loadplugins import auto_import_modules"
if ($ConnText.Contains($LegacyFusedImport)) {
    $ConnText = $ConnText.Replace(
        $LegacyFusedImport,
        "from core.kadence_behavior import render_kadence_behavior_prompt`nfrom plugins_func.loadplugins import auto_import_modules"
    )
    $ConnChanged = $true
    Write-Host "Repaired Kadence M7 legacy fused behaviour import."
}

$LegacyFusedRoot = "current_sentence_id = str(uuid.uuid4().hex)            self.sentence_id = current_sentence_id"
if ($ConnText.Contains($LegacyFusedRoot)) {
    $ConnText = $ConnText.Replace(
        $LegacyFusedRoot,
        "current_sentence_id = str(uuid.uuid4().hex)`n            self.sentence_id = current_sentence_id"
    )
    $ConnChanged = $true
    Write-Host "Repaired Kadence M7 legacy fused root-turn line."
}

$ConnImportOriginal = "from core.kadence_tool_runtime import build_kadence_tool_handler`n"
$ConnImportV1 = "from core.kadence_tool_runtime import build_kadence_tool_handler`nfrom core.kadence_behavior import render_kadence_behavior_prompt`n"
$ConnImportPatched = "from core.kadence_tool_runtime import build_kadence_tool_handler`nfrom core.kadence_behavior import render_kadence_behavior_prompt, get_kadence_behavior_snapshot`n"
if ($ConnText.Contains($ConnImportPatched)) {
    Write-Host "Kadence M7 behaviour prompt import: already applied."
}
elseif ($ConnText.Contains($ConnImportV1)) {
    $ConnText = $ConnText.Replace($ConnImportV1, $ConnImportPatched)
    $ConnChanged = $true
    Write-Host "Upgraded Kadence M7 behaviour prompt import with turn-state tracing."
}
elseif ($ConnText.Contains($ConnImportOriginal)) {
    $ConnText = $ConnText.Replace($ConnImportOriginal, $ConnImportPatched)
    $ConnChanged = $true
    Write-Host "Applied Kadence M7 behaviour prompt import."
}
else {
    throw "Kadence M7 connection import guard failed; M5 tool wiring was not found."
}

$RootOriginal = @'
        if depth == 0:
            self._kadence_tool_root_query = query
            current_sentence_id = str(uuid.uuid4().hex)
'@.Replace("`r`n", "`n")
$RootV1 = @'
        if depth == 0:
            if self.prompt:
                self.dialogue.update_system_message(
                    render_kadence_behavior_prompt(self.prompt)
                )
            self._kadence_tool_root_query = query
            current_sentence_id = str(uuid.uuid4().hex)
'@.Replace("`r`n", "`n")
$RootPatched = @'
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
'@.Replace("`r`n", "`n")
if ($ConnText.Contains($RootPatched)) {
    Write-Host "Kadence M7 top-level prompt overlay: already applied."
}
elseif ($ConnText.Contains($RootV1)) {
    $ConnText = $ConnText.Replace($RootV1, $RootPatched)
    $ConnChanged = $true
    Write-Host "Upgraded Kadence M7 top-level prompt overlay with turn-state tracing."
}
elseif ($ConnText.Contains($RootOriginal)) {
    $ConnText = $ConnText.Replace($RootOriginal, $RootPatched)
    $ConnChanged = $true
    Write-Host "Applied Kadence M7 top-level prompt overlay."
}
else {
    throw "Kadence M7 root-turn guard failed; proven M5 root-query wiring was not found."
}

foreach ($ForbiddenFusion in @(
    'render_kadence_behavior_promptfrom ',
    'uuid.uuid4().hex)            self.sentence_id'
)) {
    if ($ConnText.Contains($ForbiddenFusion)) {
        throw "Kadence M7 connection newline verification failed: $ForbiddenFusion"
    }
}

if (-not $ConnText.Contains($ConnImportPatched) -or
    -not $ConnText.Contains("render_kadence_behavior_prompt") -or
    -not $ConnText.Contains("get_kadence_behavior_snapshot") -or
    -not $ConnText.Contains("KADENCE BEHAVIOR: turn mode=") -or
    -not $ConnText.Contains("self._kadence_tool_root_query = query") -or
    -not $ConnText.Contains("self.dialogue.update_system_message(")) {
    throw "Kadence M7 connection post-patch verification failed."
}
if ($ConnChanged) {
    [System.IO.File]::WriteAllText($ConnectionPath, $ConnText, $Utf8NoBom)
    Write-Host "Kadence M7 volatile prompt overlay installed into local runtime."
}

Write-Host "Kadence M7 behaviour wiring: DEFAULT/CUSTOM, loopback-only, process-lifetime."
