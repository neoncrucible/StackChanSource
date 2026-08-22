param(
    [string]$RuntimeRoot = (Join-Path $PSScriptRoot ".runtime")
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$RepoDir = Join-Path $RuntimeRoot "xiaozhi-esp32-server"
$ConnectionPath = Join-Path $RepoDir "main\xiaozhi-server\core\connection.py"
$ToolsSource = Join-Path $PSScriptRoot "kadence_tools.py"
$RuntimeSource = Join-Path $PSScriptRoot "kadence_tool_runtime.py"
$ToolsTarget = Join-Path $RepoDir "main\xiaozhi-server\core\kadence_tools.py"
$RuntimeTarget = Join-Path $RepoDir "main\xiaozhi-server\core\kadence_tool_runtime.py"
$Utf8NoBom = [System.Text.UTF8Encoding]::new($false)

foreach ($RequiredPath in @($RepoDir, $ConnectionPath, $ToolsSource, $RuntimeSource)) {
    if (-not (Test-Path $RequiredPath)) {
        throw "Kadence M5 required path was not found: $RequiredPath"
    }
}

function Install-KadenceFile {
    param(
        [Parameter(Mandatory = $true)][string]$Source,
        [Parameter(Mandatory = $true)][string]$Target,
        [Parameter(Mandatory = $true)][string]$Label
    )

    $SourceText = [System.IO.File]::ReadAllText($Source, $Utf8NoBom)
    $TargetText = if (Test-Path $Target) {
        [System.IO.File]::ReadAllText($Target, $Utf8NoBom)
    } else {
        ""
    }

    if ($SourceText -ne $TargetText) {
        [System.IO.File]::WriteAllText($Target, $SourceText, $Utf8NoBom)
        Write-Host "Installed $Label into local runtime."
    } else {
        Write-Host "$Label already installed."
    }
}

Install-KadenceFile -Source $ToolsSource -Target $ToolsTarget -Label "Kadence M5 safe tool boundary"
Install-KadenceFile -Source $RuntimeSource -Target $RuntimeTarget -Label "Kadence M5 runtime tool adapter"

$ConnText = [System.IO.File]::ReadAllText($ConnectionPath, $Utf8NoBom).Replace("`r`n", "`n")
$ConnChanged = $false

$ImportOriginal = "from core.providers.tools.unified_tool_handler import UnifiedToolHandler`n"
$ImportPatched = "from core.providers.tools.unified_tool_handler import UnifiedToolHandler`nfrom core.kadence_tool_runtime import build_kadence_tool_handler`n"
if ($ConnText.Contains($ImportPatched)) {
    Write-Host "Kadence M5 runtime import: already applied."
}
elseif ($ConnText.Contains($ImportOriginal)) {
    $ConnText = $ConnText.Replace($ImportOriginal, $ImportPatched)
    $ConnChanged = $true
    Write-Host "Applied Kadence M5 runtime import."
}
else {
    throw "Kadence M5 import guard failed; refusing to modify runtime."
}

$IntentOriginal = @'
    def _initialize_intent(self):
        if self.intent is None:
            return
'@.Replace("`r`n", "`n")
$IntentPatched = @'
    def _initialize_intent(self):
        kadence_tool_mode = os.environ.get("KADENCE_TOOL_MODE", "").strip().lower()
        if kadence_tool_mode:
            self.intent_type = "function_call"
            self.load_function_plugin = True
            self.func_handler = build_kadence_tool_handler(
                kadence_tool_mode,
                logger=self.logger,
            )
            self.logger.bind(tag=TAG).info(
                f"KADENCE TOOLS: mode={kadence_tool_mode} allowlist={self.func_handler.current_support_functions()}"
            )
            return

        if self.intent is None:
            return
'@.Replace("`r`n", "`n")
if ($ConnText.Contains($IntentPatched)) {
    Write-Host "Kadence M5 tool-mode intent override: already applied."
}
elseif ($ConnText.Contains($IntentOriginal)) {
    $ConnText = $ConnText.Replace($IntentOriginal, $IntentPatched)
    $ConnChanged = $true
    Write-Host "Applied Kadence M5 tool-mode intent override."
}
else {
    throw "Kadence M5 intent guard failed; refusing to modify runtime."
}

$ToolInputOriginal = @'
                    tool_input = json.loads(tool_call_data.get("arguments") or "{}")
                    enqueue_tool_report(self, tool_call_data['name'], tool_input)

                    future = asyncio.run_coroutine_threadsafe(
'@.Replace("`r`n", "`n")
$ToolInputPatched = @'
                    kadence_safe_boundary = bool(
                        getattr(self.func_handler, "kadence_safe_boundary", False)
                    )
                    if kadence_safe_boundary:
                        # Do not pre-parse or report model arguments before the
                        # Kadence boundary validates them. The adapter receives
                        # the original raw argument string below.
                        tool_input = {}
                    else:
                        tool_input = json.loads(tool_call_data.get("arguments") or "{}")
                        enqueue_tool_report(self, tool_call_data['name'], tool_input)

                    future = asyncio.run_coroutine_threadsafe(
'@.Replace("`r`n", "`n")
if ($ConnText.Contains($ToolInputPatched)) {
    Write-Host "Kadence M5 pre-execution boundary guard: already applied."
}
elseif ($ConnText.Contains($ToolInputOriginal)) {
    $ConnText = $ConnText.Replace($ToolInputOriginal, $ToolInputPatched)
    $ConnChanged = $true
    Write-Host "Applied Kadence M5 pre-execution boundary guard."
}
else {
    throw "Kadence M5 pre-execution guard failed; refusing to modify runtime."
}

$SuccessReportOriginal = "                        enqueue_tool_report(self, tool_call_data['name'], tool_input, str(result.result) if result.result else None, report_tool_call=False)`n"
$SuccessReportPatched = @'
                        if not kadence_safe_boundary:
                            enqueue_tool_report(
                                self,
                                tool_call_data['name'],
                                tool_input,
                                str(result.result) if result.result else None,
                                report_tool_call=False,
                            )
'@.Replace("`r`n", "`n")
if ($ConnText.Contains($SuccessReportPatched)) {
    Write-Host "Kadence M5 success-report bypass: already applied."
}
elseif ($ConnText.Contains($SuccessReportOriginal)) {
    $ConnText = $ConnText.Replace($SuccessReportOriginal, $SuccessReportPatched)
    $ConnChanged = $true
    Write-Host "Applied Kadence M5 success-report bypass."
}
else {
    throw "Kadence M5 success-report guard failed; refusing to modify runtime."
}

$ErrorReportOriginal = "                        enqueue_tool_report(self, tool_call_data['name'], tool_input, str(e), report_tool_call=False)`n"
$ErrorReportPatched = @'
                        if not kadence_safe_boundary:
                            enqueue_tool_report(
                                self,
                                tool_call_data['name'],
                                tool_input,
                                str(e),
                                report_tool_call=False,
                            )
'@.Replace("`r`n", "`n")
if ($ConnText.Contains($ErrorReportPatched)) {
    Write-Host "Kadence M5 error-report bypass: already applied."
}
elseif ($ConnText.Contains($ErrorReportOriginal)) {
    $ConnText = $ConnText.Replace($ErrorReportOriginal, $ErrorReportPatched)
    $ConnChanged = $true
    Write-Host "Applied Kadence M5 error-report bypass."
}
else {
    throw "Kadence M5 error-report guard failed; refusing to modify runtime."
}

$DirectAnswerOriginal = @'
                    if not real_tool_calls:
                        if depth == 0:
                            self.tts.tts_text_queue.put(
'@.Replace("`r`n", "`n")
$DirectAnswerPatched = @'
                    if not real_tool_calls:
                        if depth == 0 and not self.client_abort:
                            for tc in direct_answer_calls:
                                kadence_direct_text = self._extract_direct_answer_response(
                                    tc.get("arguments", "{}")
                                )
                                kadence_direct_text = self._clean_response_garbage(
                                    kadence_direct_text or ""
                                )
                                if kadence_direct_text:
                                    self._commit_kadence_session_exchange(
                                        query,
                                        kadence_direct_text,
                                    )
                                    break
                        if depth == 0:
                            self.tts.tts_text_queue.put(
'@.Replace("`r`n", "`n")
if ($ConnText.Contains($DirectAnswerPatched)) {
    Write-Host "Kadence M5 direct-answer session commit: already applied."
}
elseif ($ConnText.Contains($DirectAnswerOriginal)) {
    $ConnText = $ConnText.Replace($DirectAnswerOriginal, $DirectAnswerPatched)
    $ConnChanged = $true
    Write-Host "Applied Kadence M5 direct-answer session commit."
}
else {
    throw "Kadence M5 direct-answer guard failed; refusing to modify runtime."
}

if (-not $ConnText.Contains("build_kadence_tool_handler") -or
    -not $ConnText.Contains('KADENCE_TOOL_MODE') -or
    -not $ConnText.Contains('kadence_safe_boundary') -or
    -not $ConnText.Contains('self._commit_kadence_session_exchange(')) {
    throw "Kadence M5 post-patch verification failed; refusing to write runtime."
}

if ($ConnChanged) {
    [System.IO.File]::WriteAllText($ConnectionPath, $ConnText, $Utf8NoBom)
    Write-Host "Kadence M5 safe tool plumbing installed into local runtime."
}
