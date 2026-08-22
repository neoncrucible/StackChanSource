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

foreach ($RequiredPath in @(
    $RepoDir,
    $ConnectionPath,
    $ToolsSource,
    $RuntimeSource
)) {
    if (-not (Test-Path $RequiredPath)) {
        throw "Kadence tools required path was not found: $RequiredPath"
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

Install-KadenceFile -Source $ToolsSource -Target $ToolsTarget -Label "Kadence safe tool boundary"
Install-KadenceFile -Source $RuntimeSource -Target $RuntimeTarget -Label "Kadence runtime tool adapter"

$ConnText = [System.IO.File]::ReadAllText($ConnectionPath, $Utf8NoBom).Replace("`r`n", "`n")
$ConnChanged = $false

$ImportOriginal = "from core.providers.tools.unified_tool_handler import UnifiedToolHandler`n"
$ImportPatched = "from core.providers.tools.unified_tool_handler import UnifiedToolHandler`nfrom core.kadence_tool_runtime import build_kadence_tool_handler`n"
if ($ConnText.Contains($ImportPatched)) {
    Write-Host "Kadence runtime tool import: already applied."
}
elseif ($ConnText.Contains($ImportOriginal)) {
    $ConnText = $ConnText.Replace($ImportOriginal, $ImportPatched)
    $ConnChanged = $true
    Write-Host "Applied Kadence runtime tool import."
}
else {
    throw "Kadence tool import guard failed; refusing to modify runtime."
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
    Write-Host "Kadence tool-mode intent override: already applied."
}
elseif ($ConnText.Contains($IntentOriginal)) {
    $ConnText = $ConnText.Replace($IntentOriginal, $IntentPatched)
    $ConnChanged = $true
    Write-Host "Applied Kadence tool-mode intent override."
}
else {
    throw "Kadence tool intent guard failed; refusing to modify runtime."
}

$FewshotOriginal = @'
        if not hasattr(self, "func_handler") or self.func_handler is None:
            return

        tools = self.func_handler.get_functions()
'@.Replace("`r`n", "`n")
$FewshotPatched = @'
        if not hasattr(self, "func_handler") or self.func_handler is None:
            return
        if getattr(self.func_handler, "kadence_safe_boundary", False):
            return

        tools = self.func_handler.get_functions()
'@.Replace("`r`n", "`n")
if ($ConnText.Contains($FewshotPatched)) {
    Write-Host "Kadence generic tool few-shot bypass: already applied."
}
elseif ($ConnText.Contains($FewshotOriginal)) {
    $ConnText = $ConnText.Replace($FewshotOriginal, $FewshotPatched)
    $ConnChanged = $true
    Write-Host "Applied Kadence generic tool few-shot bypass."
}
else {
    throw "Kadence tool few-shot guard failed; refusing to modify runtime."
}

$AdvertiseOriginal = @'
            if functions is not None and depth == 0:
                functions.append(DIRECT_ANSWER_TOOL)
'@.Replace("`r`n", "`n")
$AdvertisePatched = @'
            if (
                    functions is not None
                    and depth == 0
                    and not getattr(self.func_handler, "kadence_safe_boundary", False)
            ):
                functions.append(DIRECT_ANSWER_TOOL)
'@.Replace("`r`n", "`n")
if ($ConnText.Contains($AdvertisePatched)) {
    Write-Host "Kadence allowlist-only tool advertisement: already applied."
}
elseif ($ConnText.Contains($AdvertiseOriginal)) {
    $ConnText = $ConnText.Replace($AdvertiseOriginal, $AdvertisePatched)
    $ConnChanged = $true
    Write-Host "Applied Kadence allowlist-only tool advertisement."
}
else {
    throw "Kadence tool-advertisement guard failed; refusing to modify runtime."
}

$RootQueryOriginal = @'
        if depth == 0:
            current_sentence_id = str(uuid.uuid4().hex)
'@.Replace("`r`n", "`n")
$RootQueryPatched = @'
        if depth == 0:
            self._kadence_tool_root_query = query
            current_sentence_id = str(uuid.uuid4().hex)
'@.Replace("`r`n", "`n")
if ($ConnText.Contains($RootQueryPatched)) {
    Write-Host "Kadence tool root-query capture: already applied."
}
elseif ($ConnText.Contains($RootQueryOriginal)) {
    $ConnText = $ConnText.Replace($RootQueryOriginal, $RootQueryPatched)
    $ConnChanged = $true
    Write-Host "Applied Kadence tool root-query capture."
}
else {
    throw "Kadence tool root-query guard failed; refusing to modify runtime."
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
                        tool_input = {}
                    else:
                        tool_input = json.loads(tool_call_data.get("arguments") or "{}")
                        enqueue_tool_report(self, tool_call_data['name'], tool_input)

                    future = asyncio.run_coroutine_threadsafe(
'@.Replace("`r`n", "`n")
$ToolInputSafeMarkers = (
    $ConnText.Contains('kadence_safe_boundary = bool(') -and
    $ConnText.Contains('getattr(self.func_handler, "kadence_safe_boundary", False)') -and
    $ConnText.Contains('if kadence_safe_boundary:') -and
    $ConnText.Contains('tool_input = {}')
)
if ($ConnText.Contains($ToolInputPatched) -or $ToolInputSafeMarkers) {
    Write-Host "Kadence pre-execution boundary guard: already applied."
}
elseif ($ConnText.Contains($ToolInputOriginal)) {
    $ConnText = $ConnText.Replace($ToolInputOriginal, $ToolInputPatched)
    $ConnChanged = $true
    Write-Host "Applied Kadence pre-execution boundary guard."
}
else {
    throw "Kadence pre-execution guard failed; refusing to modify runtime."
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
$SuccessReportSafeMarkers = [regex]::IsMatch(
    $ConnText,
    '(?ms)if not kadence_safe_boundary:\s+enqueue_tool_report\(\s+self,\s+tool_call_data\[''name''\],\s+tool_input,\s+str\(result\.result\) if result\.result else None,\s+report_tool_call=False,\s+\)'
)
if ($ConnText.Contains($SuccessReportPatched) -or $SuccessReportSafeMarkers) {
    Write-Host "Kadence success-report bypass: already applied."
}
elseif ($ConnText.Contains($SuccessReportOriginal)) {
    $ConnText = $ConnText.Replace($SuccessReportOriginal, $SuccessReportPatched)
    $ConnChanged = $true
    Write-Host "Applied Kadence success-report bypass."
}
else {
    throw "Kadence success-report guard failed; refusing to modify runtime."
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
$ErrorReportSafeMarkers = [regex]::IsMatch(
    $ConnText,
    '(?ms)if not kadence_safe_boundary:\s+enqueue_tool_report\(\s+self,\s+tool_call_data\[''name''\],\s+tool_input,\s+str\(e\),\s+report_tool_call=False,\s+\)'
)
if ($ConnText.Contains($ErrorReportPatched) -or $ErrorReportSafeMarkers) {
    Write-Host "Kadence error-report bypass: already applied."
}
elseif ($ConnText.Contains($ErrorReportOriginal)) {
    $ConnText = $ConnText.Replace($ErrorReportOriginal, $ErrorReportPatched)
    $ConnChanged = $true
    Write-Host "Applied Kadence error-report bypass."
}
else {
    throw "Kadence error-report guard failed; refusing to modify runtime."
}

$RecursiveOriginal = @'
            self.chat(None, depth=depth + 1)
'@.Replace("`r`n", "`n")
$RecursivePatched = @'
            kadence_dialogue_start = len(self.dialogue.dialogue)
            self.chat(None, depth=depth + 1)
            if depth == 0 and not self.client_abort:
                kadence_root_query = getattr(self, "_kadence_tool_root_query", None)
                if kadence_root_query:
                    for kadence_message in reversed(
                        self.dialogue.dialogue[kadence_dialogue_start:]
                    ):
                        if (
                            kadence_message.role == "assistant"
                            and isinstance(kadence_message.content, str)
                            and kadence_message.content.strip()
                        ):
                            self._commit_kadence_session_exchange(
                                kadence_root_query,
                                kadence_message.content,
                            )
                            self._kadence_tool_root_query = None
                            break
'@.Replace("`r`n", "`n")
$RecursiveSafeMarkers = (
    $ConnText.Contains('kadence_dialogue_start = len(self.dialogue.dialogue)') -and
    $ConnText.Contains('kadence_root_query = getattr(self, "_kadence_tool_root_query", None)') -and
    $ConnText.Contains('self._kadence_tool_root_query = None')
)
if ($ConnText.Contains($RecursivePatched) -or $RecursiveSafeMarkers) {
    Write-Host "Kadence tool-result session commit: already applied."
}
elseif ($ConnText.Contains($RecursiveOriginal)) {
    $ConnText = $ConnText.Replace($RecursiveOriginal, $RecursivePatched)
    $ConnChanged = $true
    Write-Host "Applied Kadence tool-result session commit."
}
else {
    throw "Kadence tool-result session guard failed; refusing to modify runtime."
}

if (-not $ConnText.Contains("build_kadence_tool_handler") -or
    -not $ConnText.Contains('KADENCE_TOOL_MODE') -or
    -not $ConnText.Contains('kadence_safe_boundary') -or
    -not $ConnText.Contains('and not getattr(self.func_handler, "kadence_safe_boundary", False)') -or
    -not $ConnText.Contains('self._kadence_tool_root_query = query') -or
    -not $ConnText.Contains('kadence_dialogue_start = len(self.dialogue.dialogue)') -or
    -not $ConnText.Contains('self._commit_kadence_session_exchange(')) {
    throw "Kadence tools post-patch verification failed; refusing to write runtime."
}

if ($ConnChanged) {
    [System.IO.File]::WriteAllText($ConnectionPath, $ConnText, $Utf8NoBom)
    Write-Host "Kadence safe tool plumbing installed into local runtime."
}
