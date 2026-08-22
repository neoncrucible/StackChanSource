param(
    [Parameter(Mandatory = $true)][string]$RepoDir
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

# Active Alpha 2 runtime patch path after Gemini retirement. The pinned Xiaozhi
# checkout remains immutable in Git; only the ignored local runtime is patched.
$SileroProvider = Join-Path $RepoDir "main\xiaozhi-server\core\providers\vad\silero.py"
$RuntimeConfig = Join-Path $RepoDir "main\xiaozhi-server\data\.config.yaml"
$TemplateConfig = Join-Path $PSScriptRoot "kadence.config.example.yaml"
$KadenceSessionSource = Join-Path $PSScriptRoot "kadence_session.py"
$KadenceSessionTarget = Join-Path $RepoDir "main\xiaozhi-server\core\kadence_session.py"
$WebSocketServer = Join-Path $RepoDir "main\xiaozhi-server\core\websocket_server.py"
$ConnectionHandler = Join-Path $RepoDir "main\xiaozhi-server\core\connection.py"
$Utf8NoBom = [System.Text.UTF8Encoding]::new($false)

foreach ($RequiredPath in @(
    $SileroProvider,
    $RuntimeConfig,
    $TemplateConfig,
    $KadenceSessionSource,
    $WebSocketServer,
    $ConnectionHandler
)) {
    if (-not (Test-Path $RequiredPath)) {
        throw "Kadence runtime required path was not found: $RequiredPath"
    }
}

# Preserve the narrow Alpha 1 encoding-repair capability, now with one Project
# credential source only. The first api_key in the proven template is OpenAI.
$ConfigText = [System.IO.File]::ReadAllText($RuntimeConfig, $Utf8NoBom)
$IllegalYamlControls = '[\x00-\x08\x0B\x0C\x0E-\x1F\x7F-\x9F]'
if ([regex]::IsMatch($ConfigText, $IllegalYamlControls)) {
    $ApiKeys = [regex]::Matches(
        $ConfigText,
        '(?m)^[ \t]+api_key:[ \t]*(.+?)[ \t]*$'
    )
    if ($ApiKeys.Count -lt 1) {
        throw "Runtime YAML is encoding-corrupted and the OpenAI API key could not be recovered safely. Refusing to overwrite it."
    }

    $OpenAiKey = $ApiKeys[0].Groups[1].Value.Trim()
    if ([string]::IsNullOrWhiteSpace($OpenAiKey)) {
        throw "Runtime YAML is encoding-corrupted and the recovered OpenAI API key was empty."
    }

    $TemplateText = [System.IO.File]::ReadAllText($TemplateConfig, $Utf8NoBom)
    $ConfigText = $TemplateText.Replace("REPLACE_WITH_OPENAI_API_KEY", $OpenAiKey)
    [System.IO.File]::WriteAllText($RuntimeConfig, $ConfigText, $Utf8NoBom)
    Write-Host "Repaired Alpha runtime YAML encoding from Luna-only template; OpenAI key preserved locally."
}

# Pinned Xiaozhi bypasses Silero in manual-listen mode. Kadence still needs the
# real Silero state for server-side endpoint detection while every manual frame
# continues to be buffered exactly as in the frozen Alpha 1 transport contract.
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

# M4 volatile session continuity.
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

$WsAttachOriginal = @'
        try:
            await handler.handle_connection(websocket)
'@.Replace("`r`n", "`n")
$WsAttachPatched = @'
        handler.kadence_session_history = self.kadence_session_history
        try:
            await handler.handle_connection(websocket)
'@.Replace("`r`n", "`n")
if ($WsText.Contains($WsAttachPatched)) {
    Write-Host "Kadence M4 handler session attachment: already applied."
}
elseif ($WsText.Contains($WsAttachOriginal)) {
    $WsText = $WsText.Replace($WsAttachOriginal, $WsAttachPatched)
    $WsChanged = $true
    Write-Host "Applied Kadence M4 handler session attachment."
}
else {
    throw "Kadence M4 handler attachment guard failed; refusing to modify runtime."
}

if (-not $WsText.Contains("KadenceSessionHistory") -or
    -not $WsText.Contains("handler.kadence_session_history = self.kadence_session_history")) {
    throw "Kadence M4 WebSocket post-patch verification failed."
}
if ($WsChanged) {
    [System.IO.File]::WriteAllText($WebSocketServer, $WsText, $Utf8NoBom)
    Write-Host "Kadence M4 WebSocket process-session ownership installed."
}

$ConnText = [System.IO.File]::ReadAllText($ConnectionHandler, $Utf8NoBom).Replace("`r`n", "`n")
$ConnChanged = $false
$ConnStateOriginal = @'
        self.session_id = str(uuid.uuid4())
        self.logger = setup_logging()
'@.Replace("`r`n", "`n")
$ConnStatePatched = @'
        self.session_id = str(uuid.uuid4())
        self.logger = setup_logging()
        self.kadence_session_history = None
        self._kadence_history_hydrated = False
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

$ConnHydrateCallOriginal = "            self._init_prompt_enhancement()`n"
$ConnHydrateCallPatched = "            self._init_prompt_enhancement()`n            self._hydrate_kadence_session_history()`n"
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
