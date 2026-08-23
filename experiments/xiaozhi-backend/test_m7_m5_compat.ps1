$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = $PSScriptRoot
$Wrapper = Join-Path $Root "apply_kadence_tools_compat_windows.ps1"
if (-not (Test-Path $Wrapper)) {
    throw "Missing M7/M5 compatibility wrapper: $Wrapper"
}

$TempRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("kadence-m7-m5-compat-" + [guid]::NewGuid().ToString("N"))
$CoreDir = Join-Path $TempRoot "xiaozhi-esp32-server/main/xiaozhi-server/core"
New-Item -ItemType Directory -Force -Path $CoreDir | Out-Null
$ConnectionPath = Join-Path $CoreDir "connection.py"

# Representative already-valid M5 runtime after M7 has wrapped the root turn.
$ConnectionText = @'
from core.kadence_tool_runtime import build_kadence_tool_handler
KADENCE_TOOL_MODE = "marker"
kadence_safe_boundary = True
and not getattr(self.func_handler, "kadence_safe_boundary", False)

        if depth == 0:
            if self.prompt:
                self.dialogue.update_system_message(
                    render_kadence_behavior_prompt(self.prompt)
                )
            self._kadence_tool_root_query = query
            current_sentence_id = str(uuid.uuid4().hex)

            kadence_dialogue_start = len(self.dialogue.dialogue)
            self._commit_kadence_session_exchange(
'@
[System.IO.File]::WriteAllText($ConnectionPath,$ConnectionText,[System.Text.UTF8Encoding]::new($false))

try {
    $Output = (& $Wrapper -RuntimeRoot $TempRoot 2>&1 | Out-String)
    if (-not $Output.Contains("legacy patcher skipped for M7 compatibility")) {
        throw "FAIL  M7-enhanced valid M5 runtime was not preserved. Output: $Output"
    }
    Write-Host "PASS  M7-enhanced valid M5 runtime skips legacy textual patcher"

    # Guard remains fail-closed if root capture is duplicated.
    [System.IO.File]::AppendAllText(
        $ConnectionPath,
        "`n            self._kadence_tool_root_query = query`n",
        [System.Text.UTF8Encoding]::new($false)
    )
    $FailedClosed = $false
    try {
        & $Wrapper -RuntimeRoot $TempRoot | Out-Null
    }
    catch {
        if ($_.Exception.Message -match "expected exactly one root-query capture") {
            $FailedClosed = $true
        } else {
            throw
        }
    }
    if (-not $FailedClosed) {
        throw "FAIL  duplicated M5 root-query capture was not rejected."
    }
    Write-Host "PASS  ambiguous duplicated root capture still fails closed"
}
finally {
    Remove-Item $TempRoot -Recurse -Force -ErrorAction SilentlyContinue
}

Write-Host "M7/M5 compatibility test: PASS"
