param(
    [string]$RuntimeRoot = (Join-Path $PSScriptRoot ".runtime")
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$LegacyApplier = Join-Path $PSScriptRoot "apply_kadence_tools_windows.ps1"
$ConnectionPath = Join-Path $RuntimeRoot "xiaozhi-esp32-server\main\xiaozhi-server\core\connection.py"
$Utf8NoBom = [System.Text.UTF8Encoding]::new($false)

foreach ($RequiredPath in @($LegacyApplier, $ConnectionPath)) {
    if (-not (Test-Path $RequiredPath)) {
        throw "Kadence M5 compatibility wrapper required path was not found: $RequiredPath"
    }
}

$ConnText = [System.IO.File]::ReadAllText($ConnectionPath, $Utf8NoBom).Replace("`r`n", "`n")

# M7 legitimately wraps the M5 root-turn capture with prompt-overlay logic. The
# original M5 patcher predates that shape and therefore cannot prove idempotence
# from its old exact block. If every M5 authority marker is already present,
# preserve the enhanced runtime and skip the old textual patcher entirely.
$M5Markers = @(
    'build_kadence_tool_handler',
    'KADENCE_TOOL_MODE',
    'kadence_safe_boundary',
    'and not getattr(self.func_handler, "kadence_safe_boundary", False)',
    'self._kadence_tool_root_query = query',
    'kadence_dialogue_start = len(self.dialogue.dialogue)',
    'self._commit_kadence_session_exchange('
)

$Missing = @($M5Markers | Where-Object { -not $ConnText.Contains($_) })
if ($Missing.Count -eq 0) {
    $RootCaptureCount = [regex]::Matches(
        $ConnText,
        '(?m)^            self\._kadence_tool_root_query = query\s*$'
    ).Count
    if ($RootCaptureCount -ne 1) {
        throw "Kadence M5 compatibility guard failed: expected exactly one root-query capture, found $RootCaptureCount."
    }

    Write-Host "Kadence safe tool boundary already satisfies M5 authority markers; legacy patcher skipped for M7 compatibility."
    return
}

Write-Host "Kadence M5 authority markers incomplete; running proven M5 patcher."
& $LegacyApplier -RuntimeRoot $RuntimeRoot
