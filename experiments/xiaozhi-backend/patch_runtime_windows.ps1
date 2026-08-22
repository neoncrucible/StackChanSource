param(
    [Parameter(Mandatory = $true)][string]$RepoDir
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

# Keep the pinned Xiaozhi checkout immutable in Git and make only narrowly
# guarded compatibility edits to the ignored local runtime.
$GeminiProvider = Join-Path $RepoDir "main\xiaozhi-server\core\providers\llm\gemini\gemini.py"
$SileroProvider = Join-Path $RepoDir "main\xiaozhi-server\core\providers\vad\silero.py"
$RuntimeConfig = Join-Path $RepoDir "main\xiaozhi-server\data\.config.yaml"
$TemplateConfig = Join-Path $PSScriptRoot "kadence.config.example.yaml"
$KadenceSessionSource = Join-Path $PSScriptRoot "kadence_session.py"
$KadenceSessionTarget = Join-Path $RepoDir "main\xiaozhi-server\core\kadence_session.py"
$WebSocketServer = Join-Path $RepoDir "main\xiaozhi-server\core\websocket_server.py"
$ConnectionHandler = Join-Path $RepoDir "main\xiaozhi-server\core\connection.py"
$Utf8NoBom = [System.Text.UTF8Encoding]::new($false)

if (-not (Test-Path $GeminiProvider)) {
    throw "Pinned Xiaozhi Gemini provider was not found: $GeminiProvider"
}
if (-not (Test-Path $SileroProvider)) {
    throw "Pinned Xiaozhi Silero provider was not found: $SileroProvider"
}
if (-not (Test-Path $RuntimeConfig)) {
    throw "Pinned Xiaozhi runtime config was not found: $RuntimeConfig"
}
if (-not (Test-Path $TemplateConfig)) {
    throw "Kadence Alpha config template was not found: $TemplateConfig"
}
if (-not (Test-Path $KadenceSessionSource)) {
    throw "Kadence M4 session helper was not found: $KadenceSessionSource"
}
if (-not (Test-Path $WebSocketServer)) {
    throw "Pinned Xiaozhi WebSocket server was not found: $WebSocketServer"
}
if (-not (Test-Path $ConnectionHandler)) {
    throw "Pinned Xiaozhi connection handler was not found: $ConnectionHandler"
}

# Always read/write these files as UTF-8 explicitly. Windows PowerShell 5.1
# otherwise uses its legacy default text encoding and can corrupt non-ASCII
# punctuation in YAML comments during an in-place migration.
$ProviderText = [System.IO.File]::ReadAllText($GeminiProvider, $Utf8NoBom)
$ProviderChanged = $false

# google-generativeai==0.8.5 does not accept a top-level `timeout=` argument on
# GenerativeModel.generate_content(). Per-request transport settings belong in
# `request_options`.
$TimeoutOriginal = "            timeout=self.timeout,"
$TimeoutReplacement = '            request_options={"timeout": self.timeout},'
if ($ProviderText.Contains($TimeoutReplacement)) {
    Write-Host "Xiaozhi Gemini timeout compatibility patch: already applied."
}
elseif ($ProviderText.Contains($TimeoutOriginal)) {
    $ProviderText = $ProviderText.Replace($TimeoutOriginal, $TimeoutReplacement)
    $ProviderChanged = $true
    Write-Host "Applied Xiaozhi Gemini compatibility patch: timeout -> request_options.timeout"
}
else {
    throw "Gemini timeout compatibility patch guard failed. Expected pinned call was not found; refusing to modify runtime."
}

# Gemini 3.x deprecates the legacy sampling parameters used by this pinned
# provider. Keep only the output-token ceiling for the Alpha 1 latency baseline.
$SamplingOriginal = @"
        self.gen_cfg = GenerationConfig(
            temperature=0.7,
            top_p=0.9,
            top_k=40,
            max_output_tokens=2048,
        )
"@
$SamplingReplacement = @"
        self.gen_cfg = GenerationConfig(
            max_output_tokens=2048,
        )
"@

if ($ProviderText.Contains($SamplingReplacement)) {
    Write-Host "Xiaozhi Gemini 3.x generation-config patch: already applied."
}
elseif ($ProviderText.Contains($SamplingOriginal)) {
    $ProviderText = $ProviderText.Replace($SamplingOriginal, $SamplingReplacement)
    $ProviderChanged = $true
    Write-Host "Applied Xiaozhi Gemini 3.x generation-config patch: removed deprecated sampling parameters."
}
else {
    throw "Gemini generation-config patch guard failed. Expected pinned GenerationConfig block was not found; refusing to modify runtime config."
}

if ($ProviderChanged) {
    [System.IO.File]::WriteAllText($GeminiProvider, $ProviderText, $Utf8NoBom)
}

$ConfigText = [System.IO.File]::ReadAllText($RuntimeConfig, $Utf8NoBom)

# Repair the specific Windows encoding failure seen during Alpha 1 migration.
# Preserve the two already-entered credentials locally, rebuild from the clean
# checked-in template, and never print either secret.
$IllegalYamlControls = '[\x00-\x08\x0B\x0C\x0E-\x1F\x7F-\x9F]'
if ([regex]::IsMatch($ConfigText, $IllegalYamlControls)) {
    $ApiKeys = [regex]::Matches(
        $ConfigText,
        '(?m)^[ \t]+api_key:[ \t]*(.+?)[ \t]*$'
    )
    if ($ApiKeys.Count -ne 2) {
        throw "Runtime YAML is encoding-corrupted and its two API keys could not be recovered safely. Refusing to overwrite it."
    }

    $OpenAiKey = $ApiKeys[0].Groups[1].Value.Trim()
    $GeminiKey = $ApiKeys[1].Groups[1].Value.Trim()
    if ([string]::IsNullOrWhiteSpace($OpenAiKey) -or
        [string]::IsNullOrWhiteSpace($GeminiKey)) {
        throw "Runtime YAML is encoding-corrupted and one recovered API key was empty. Refusing to overwrite it."
    }

    $TemplateText = [System.IO.File]::ReadAllText($TemplateConfig, $Utf8NoBom)
    $ConfigText = $TemplateText.Replace("REPLACE_WITH_OPENAI_API_KEY", $OpenAiKey)
    $ConfigText = $ConfigText.Replace("REPLACE_WITH_GEMINI_API_KEY", $GeminiKey)
    [System.IO.File]::WriteAllText($RuntimeConfig, $ConfigText, $Utf8NoBom)
    Write-Host "Repaired Alpha runtime YAML encoding from clean template; existing API keys preserved locally."
}

# Alpha 1 is a latency baseline. Gemini 3.6 Flash defaults to medium thinking,
# which can exceed the robot's 30-second response watchdog. Flash-Lite defaults
# to minimal thinking and is the proven baseline for spoken turn latency.
$RetiredModel = '    model_name: "gemini-2.0-flash"'
$SlowModel = '    model_name: "gemini-3.6-flash"'
$TargetModel = '    model_name: "gemini-3.5-flash-lite"'

if ($ConfigText.Contains($TargetModel)) {
    Write-Host "Kadence Gemini model: gemini-3.5-flash-lite already configured."
}
elseif ($ConfigText.Contains($SlowModel)) {
    $ConfigText = $ConfigText.Replace($SlowModel, $TargetModel)
    [System.IO.File]::WriteAllText($RuntimeConfig, $ConfigText, $Utf8NoBom)
    Write-Host "Migrated Kadence Gemini model: gemini-3.6-flash -> gemini-3.5-flash-lite"
}
elseif ($ConfigText.Contains($RetiredModel)) {
    $ConfigText = $ConfigText.Replace($RetiredModel, $TargetModel)
    [System.IO.File]::WriteAllText($RuntimeConfig, $ConfigText, $Utf8NoBom)
    Write-Host "Migrated Kadence Gemini model: gemini-2.0-flash -> gemini-3.5-flash-lite"
}
else {
    throw "Gemini model migration guard failed. Expected an Alpha model line was not found; refusing to modify runtime config."
}

# Pinned Xiaozhi deliberately bypasses Silero in manual-listen mode. Kadence
# still needs the real Silero state for server-side endpoint detection, while
# Xiaozhi must continue buffering every manual-mode frame. Patch the runtime so
# Silero observes the frame, stores its state on the connection, then returns
# True to preserve the original manual buffering contract.
$VadText = [System.IO.File]::ReadAllText($SileroProvider, $Utf8NoBom).Replace("`r`n", "`n")

$ManualOriginal = "        if conn.client_listen_mode == `"manual`":`n            return True`n`n"
$ManualDiagnostic = "        kadence_manual_diagnostics = conn.client_listen_mode == `"manual`"`n`n"
$ManualEndpoint = "        kadence_manual_endpoint_vad = conn.client_listen_mode == `"manual`"`n`n"

$VadReturnOriginal = @'
            return client_have_voice
        except Exception as e:
'@.Replace("`r`n", "`n")

$VadReturnDiagnostic = @'
            if kadence_manual_diagnostics:
                previous = getattr(conn, "_kadence_diag_vad_state", None)
                if previous is None or previous != client_have_voice:
                    logger.bind(tag=TAG).info(
                        f"KADENCE SERVER VAD: {'SPEECH' if client_have_voice else 'SILENCE'}"
                    )
                    conn._kadence_diag_vad_state = client_have_voice
                return True
            return client_have_voice
        except Exception as e:
'@.Replace("`r`n", "`n")

$VadReturnEndpoint = @'
            if kadence_manual_endpoint_vad:
                conn._kadence_server_vad_state = client_have_voice
                return True
            return client_have_voice
        except Exception as e:
'@.Replace("`r`n", "`n")

$VadChanged = $false
if ($VadText.Contains($ManualEndpoint)) {
    Write-Host "Kadence manual-mode Silero endpoint observer: already applied."
}
elseif ($VadText.Contains($ManualDiagnostic)) {
    $VadText = $VadText.Replace($ManualDiagnostic, $ManualEndpoint)
    $VadChanged = $true
    Write-Host "Migrated Kadence manual-mode Silero diagnostic hook to endpoint observer."
}
elseif ($VadText.Contains($ManualOriginal)) {
    $VadText = $VadText.Replace($ManualOriginal, $ManualEndpoint)
    $VadChanged = $true
    Write-Host "Applied Kadence manual-mode Silero endpoint observer."
}
else {
    throw "Silero endpoint patch guard failed: manual-mode executable bypass was not found."
}

if ($VadText.Contains($VadReturnEndpoint)) {
    Write-Host "Kadence Silero endpoint state export: already applied."
}
elseif ($VadText.Contains($VadReturnDiagnostic)) {
    $VadText = $VadText.Replace($VadReturnDiagnostic, $VadReturnEndpoint)
    $VadChanged = $true
    Write-Host "Removed temporary Silero edge logger; retained endpoint state export."
}
elseif ($VadText.Contains($VadReturnOriginal)) {
    $VadText = $VadText.Replace($VadReturnOriginal, $VadReturnEndpoint)
    $VadChanged = $true
    Write-Host "Applied Kadence Silero endpoint state export."
}
else {
    throw "Silero endpoint patch guard failed: VAD return site was not found."
}

if (-not $VadText.Contains($ManualEndpoint) -or
    -not $VadText.Contains('_kadence_server_vad_state')) {
    throw "Silero endpoint post-patch verification failed; refusing to write runtime."
}

if ($VadChanged) {
    [System.IO.File]::WriteAllText($SileroProvider, $VadText, $Utf8NoBom)
    Write-Host "Kadence manual-mode Silero endpoint observer installed (buffering semantics unchanged)."
}

# Milestone 4: install the Project-owned volatile session helper into the ignored
# pinned runtime. This is deliberately separate from Xiaozhi's Memory provider:
# it stores only short user/assistant exchanges for the life of this backend
# process and contains no provider-specific code or durable storage.
$SessionSourceText = [System.IO.File]::ReadAllText($KadenceSessionSource, $Utf8NoBom)
$SessionTargetText = if (Test-Path $KadenceSessionTarget) {
    [System.IO.File]::ReadAllText($KadenceSessionTarget, $Utf8NoBom)
} else {
    ""
}
if ($SessionTargetText -ne $SessionSourceText) {
    [System.IO.File]::WriteAllText($KadenceSessionTarget, $SessionSourceText, $Utf8NoBom)
    Write-Host "Installed Kadence M4 volatile session helper into local runtime."
} else {
    Write-Host "Kadence M4 volatile session helper: already installed."
}

# Own session state at WebSocketServer/process scope rather than inside Luna,
# Gemini or a per-socket ConnectionHandler. Each new handler receives the same
# in-memory store; backend restart naturally destroys it.
$WsText = [System.IO.File]::ReadAllText($WebSocketServer, $Utf8NoBom).Replace("`r`n", "`n")
$WsChanged = $false

$WsImportOriginal = "from core.connection import ConnectionHandler`n"
$WsImportPatched = "from core.connection import ConnectionHandler`nfrom core.kadence_session import KadenceSessionHistory`n"
if ($WsText.Contains($WsImportPatched)) {
    Write-Host "Kadence M4 WebSocket session import: already applied."
}
elseif ($WsText.Contains($WsImportOriginal)) {
    $WsText = $WsText.Replace($WsImportOriginal, $WsImportPatched)
    $WsChanged = $true
    Write-Host "Applied Kadence M4 WebSocket session import."
}
else {
    throw "Kadence M4 WebSocket import guard failed; refusing to modify runtime."
}

$WsInitOriginal = @'
        self.logger = setup_logging(config)
        self.config_lock = asyncio.Lock()
'@.Replace("`r`n", "`n")
$WsInitPatched = @'
        self.logger = setup_logging(config)
        self.config_lock = asyncio.Lock()
        self.kadence_session_history = KadenceSessionHistory(
            max_exchanges=8,
            max_chars=12_000,
        )
'@.Replace("`r`n", "`n")

if ($WsText.Contains($WsInitPatched)) {
    Write-Host "Kadence M4 process-lifetime session store: already applied."
}
elseif ($WsText.Contains($WsInitOriginal)) {
    $WsText = $WsText.Replace($WsInitOriginal, $WsInitPatched)
    $WsChanged = $true
    Write-Host "Applied Kadence M4 process-lifetime session store."
}
else {
    throw "Kadence M4 WebSocket init guard failed; refusing to modify runtime."
}

$WsHandlerOriginal = @'
        handler = ConnectionHandler(
            self.config,
            self._vad,
            self._asr,
            self._llm,
            self._memory,
            self._intent,
            self,  # 传入server实例
        )
'@.Replace("`r`n", "`n")
$WsHandlerPatched = @'
        handler = ConnectionHandler(
            self.config,
            self._vad,
            self._asr,
            self._llm,
            self._memory,
            self._intent,
            self,  # 传入server实例
            session_history=self.kadence_session_history,
        )
'@.Replace("`r`n", "`n")

if ($WsText.Contains($WsHandlerPatched)) {
    Write-Host "Kadence M4 handler session injection: already applied."
}
elseif ($WsText.Contains($WsHandlerOriginal)) {
    $WsText = $WsText.Replace($WsHandlerOriginal, $WsHandlerPatched)
    $WsChanged = $true
    Write-Host "Applied Kadence M4 handler session injection."
}
else {
    throw "Kadence M4 handler injection guard failed; refusing to modify runtime."
}

if (-not $WsText.Contains("KadenceSessionHistory") -or
    -not $WsText.Contains("session_history=self.kadence_session_history")) {
    throw "Kadence M4 WebSocket post-patch verification failed."
}

if ($WsChanged) {
    [System.IO.File]::WriteAllText($WebSocketServer, $WsText, $Utf8NoBom)
    Write-Host "Kadence M4 WebSocket process-session ownership installed."
}

# Hydrate a fresh per-socket Dialogue from the process store after canonical
# system-prompt construction, then commit only completed top-level spoken turns
# back into that store. Provider adapters continue receiving the same generic
# Dialogue they already consume.
$ConnText = [System.IO.File]::ReadAllText($ConnectionHandler, $Utf8NoBom).Replace("`r`n", "`n")
$ConnChanged = $false

$ConnSignatureOriginal = @'
            _intent,
            server=None,
    ):
'@.Replace("`r`n", "`n")
$ConnSignaturePatched = @'
            _intent,
            server=None,
            session_history=None,
    ):
'@.Replace("`r`n", "`n")

if ($ConnText.Contains($ConnSignaturePatched)) {
    Write-Host "Kadence M4 ConnectionHandler session parameter: already applied."
}
elseif ($ConnText.Contains($ConnSignatureOriginal)) {
    $ConnText = $ConnText.Replace($ConnSignatureOriginal, $ConnSignaturePatched)
    $ConnChanged = $true
    Write-Host "Applied Kadence M4 ConnectionHandler session parameter."
}
else {
    throw "Kadence M4 ConnectionHandler signature guard failed; refusing to modify runtime."
}

$ConnStateOriginal = @'
        self.server = server  # 保存server实例的引用

        self.need_bind = False  # 是否需要绑定设备
'@.Replace("`r`n", "`n")
$ConnStatePatched = @'
        self.server = server  # 保存server实例的引用
        self.kadence_session_history = session_history
        self._kadence_history_hydrated = False

        self.need_bind = False  # 是否需要绑定设备
'@.Replace("`r`n", "`n")

if ($ConnText.Contains($ConnStatePatched)) {
    Write-Host "Kadence M4 ConnectionHandler session state: already applied."
}
elseif ($ConnText.Contains($ConnStateOriginal)) {
    $ConnText = $ConnText.Replace($ConnStateOriginal, $ConnStatePatched)
    $ConnChanged = $true
    Write-Host "Applied Kadence M4 ConnectionHandler session state."
}
else {
    throw "Kadence M4 ConnectionHandler state guard failed; refusing to modify runtime."
}

$ConnHydrateCallOriginal = @'
            self._init_prompt_enhancement()
            """注入工具调用few-shot示例（仅function_call模式）"""
'@.Replace("`r`n", "`n")
$ConnHydrateCallPatched = @'
            self._init_prompt_enhancement()
            self._hydrate_kadence_session_history()
            """注入工具调用few-shot示例（仅function_call模式）"""
'@.Replace("`r`n", "`n")

if ($ConnText.Contains($ConnHydrateCallPatched)) {
    Write-Host "Kadence M4 dialogue hydration call: already applied."
}
elseif ($ConnText.Contains($ConnHydrateCallOriginal)) {
    $ConnText = $ConnText.Replace($ConnHydrateCallOriginal, $ConnHydrateCallPatched)
    $ConnChanged = $true
    Write-Host "Applied Kadence M4 dialogue hydration call."
}
else {
    throw "Kadence M4 hydration-call guard failed; refusing to modify runtime."
}

$ConnMethodsAnchor = @'
    def change_system_prompt(self, prompt):
'@.Replace("`r`n", "`n")
$ConnMethodsPatched = @'
    def _hydrate_kadence_session_history(self):
        if self._kadence_history_hydrated:
            return
        self._kadence_history_hydrated = True

        if self.kadence_session_history is None or not self.device_id:
            return

        messages = self.kadence_session_history.get_messages(self.device_id)
        for item in messages:
            role = item.get("role")
            content = item.get("content")
            if role in ("user", "assistant") and isinstance(content, str) and content:
                self.dialogue.put(Message(role=role, content=content))

        if messages:
            self.logger.bind(tag=TAG).info(
                f"KADENCE SESSION: hydrated {len(messages) // 2} exchange(s)"
            )

    def _commit_kadence_session_exchange(self, query, assistant_text):
        if self.kadence_session_history is None or not self.device_id:
            return

        retained = self.kadence_session_history.append_exchange(
            self.device_id,
            query,
            assistant_text,
        )
        if retained:
            count = self.kadence_session_history.exchange_count(self.device_id)
            self.logger.bind(tag=TAG).info(
                f"KADENCE SESSION: retained exchange count={count}"
            )

    def change_system_prompt(self, prompt):
'@.Replace("`r`n", "`n")

if ($ConnText.Contains("    def _hydrate_kadence_session_history(self):`n")) {
    Write-Host "Kadence M4 session helper methods: already applied."
}
elseif ($ConnText.Contains($ConnMethodsAnchor)) {
    $ConnText = $ConnText.Replace($ConnMethodsAnchor, $ConnMethodsPatched)
    $ConnChanged = $true
    Write-Host "Applied Kadence M4 session helper methods."
}
else {
    throw "Kadence M4 helper-method guard failed; refusing to modify runtime."
}

$ConnCommitOriginal = @'
        if len(response_message) > 0:
            text_buff = "".join(response_message)
            self.tts.store_tts_text(current_sentence_id, text_buff)
            self.dialogue.put(Message(role="assistant", content=text_buff))

        if depth == 0:
'@.Replace("`r`n", "`n")
$ConnCommitPatched = @'
        if len(response_message) > 0:
            text_buff = "".join(response_message)
            self.tts.store_tts_text(current_sentence_id, text_buff)
            self.dialogue.put(Message(role="assistant", content=text_buff))
            if depth == 0 and not self.client_abort:
                self._commit_kadence_session_exchange(query, text_buff)

        if depth == 0:
'@.Replace("`r`n", "`n")

if ($ConnText.Contains($ConnCommitPatched)) {
    Write-Host "Kadence M4 completed-turn commit: already applied."
}
elseif ($ConnText.Contains($ConnCommitOriginal)) {
    $ConnText = $ConnText.Replace($ConnCommitOriginal, $ConnCommitPatched)
    $ConnChanged = $true
    Write-Host "Applied Kadence M4 completed-turn commit."
}
else {
    throw "Kadence M4 completed-turn commit guard failed; refusing to modify runtime."
}

if (-not $ConnText.Contains("self._hydrate_kadence_session_history()") -or
    -not $ConnText.Contains("self._commit_kadence_session_exchange(query, text_buff)")) {
    throw "Kadence M4 ConnectionHandler post-patch verification failed."
}

if ($ConnChanged) {
    [System.IO.File]::WriteAllText($ConnectionHandler, $ConnText, $Utf8NoBom)
    Write-Host "Kadence M4 ConnectionHandler session continuity installed."
}
