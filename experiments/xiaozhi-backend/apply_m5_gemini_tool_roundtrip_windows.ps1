param(
    [string]$RuntimeRoot = (Join-Path $PSScriptRoot ".runtime")
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$RepoDir = Join-Path $RuntimeRoot "xiaozhi-esp32-server"
$GeminiProviderPath = Join-Path $RepoDir "main\xiaozhi-server\core\providers\llm\gemini\gemini.py"
$Utf8NoBom = [System.Text.UTF8Encoding]::new($false)

if (-not (Test-Path $GeminiProviderPath)) {
    throw "Kadence M5 Gemini provider was not found: $GeminiProviderPath"
}

$Text = [System.IO.File]::ReadAllText($GeminiProviderPath, $Utf8NoBom).Replace("`r`n", "`n")
$Changed = $false

# Gemini 3 requires the opaque thought signature returned on a functionCall to
# be replayed on the same functionCall part when the tool result is submitted.
# Keep that provider metadata local to the Gemini adapter and key it by the
# generic Xiaozhi tool-call id so Kadence's Project-owned tool boundary remains
# provider-neutral.
$CacheOriginal = @'
        self.gen_cfg = GenerationConfig(
            max_output_tokens=2048,
        )
'@.Replace("`r`n", "`n")
$CachePatched = @'
        self.gen_cfg = GenerationConfig(
            max_output_tokens=2048,
        )

        # Provider-local metadata needed only for Gemini tool round-trips.
        # Values may include opaque thought-signature bytes; never log them.
        self._kadence_tool_call_context = {}
'@.Replace("`r`n", "`n")

if ($Text.Contains($CachePatched)) {
    Write-Host "Kadence M5 Gemini tool-call context cache: already applied."
}
elseif ($Text.Contains($CacheOriginal)) {
    $Text = $Text.Replace($CacheOriginal, $CachePatched)
    $Changed = $true
    Write-Host "Applied Kadence M5 Gemini tool-call context cache."
}
else {
    throw "Kadence M5 Gemini context-cache guard failed; refusing to modify runtime."
}

$HistoryOriginal = @'
            if r == "assistant" and "tool_calls" in m:
                tc = m["tool_calls"][0]
                contents.append(
                    {
                        "role": "model",
                        "parts": [
                            {
                                "function_call": {
                                    "name": tc["function"]["name"],
                                    "args": json.loads(tc["function"]["arguments"]),
                                }
                            }
                        ],
                    }
                )
                continue

            if r == "tool":
                contents.append(
                    {
                        "role": "model",
                        "parts": [{"text": str(m.get("content", ""))}],
                    }
                )
                continue
'@.Replace("`r`n", "`n")
$HistoryPatched = @'
            if r == "assistant" and "tool_calls" in m:
                tc = m["tool_calls"][0]
                kadence_part = {
                    "function_call": {
                        "name": tc["function"]["name"],
                        "args": json.loads(tc["function"]["arguments"]),
                    }
                }
                kadence_context = self._kadence_tool_call_context.get(
                    tc.get("id"), {}
                )
                kadence_signature = kadence_context.get("thought_signature")
                if kadence_signature:
                    kadence_part["thought_signature"] = kadence_signature
                contents.append(
                    {
                        "role": "model",
                        "parts": [kadence_part],
                    }
                )
                continue

            if r == "tool":
                kadence_context = self._kadence_tool_call_context.get(
                    m.get("tool_call_id"), {}
                )
                kadence_tool_name = kadence_context.get("name")
                if kadence_tool_name:
                    kadence_raw_result = m.get("content", "")
                    try:
                        kadence_result = json.loads(kadence_raw_result or "{}")
                    except (json.JSONDecodeError, TypeError):
                        kadence_result = {"result": str(kadence_raw_result)}
                    if not isinstance(kadence_result, dict):
                        kadence_result = {"result": kadence_result}
                    contents.append(
                        {
                            "role": "user",
                            "parts": [
                                {
                                    "function_response": {
                                        "name": kadence_tool_name,
                                        "response": kadence_result,
                                    }
                                }
                            ],
                        }
                    )
                else:
                    # Preserve pinned behaviour for any unrelated/legacy tool
                    # message that was not produced by this Gemini provider.
                    contents.append(
                        {
                            "role": "model",
                            "parts": [{"text": str(m.get("content", ""))}],
                        }
                    )
                continue
'@.Replace("`r`n", "`n")

if ($Text.Contains($HistoryPatched)) {
    Write-Host "Kadence M5 Gemini signed tool history: already applied."
}
elseif ($Text.Contains($HistoryOriginal)) {
    $Text = $Text.Replace($HistoryOriginal, $HistoryPatched)
    $Changed = $true
    Write-Host "Applied Kadence M5 Gemini signed tool history/functionResponse mapping."
}
else {
    throw "Kadence M5 Gemini tool-history guard failed; refusing to modify runtime."
}

$CaptureOriginal = @'
                    if getattr(part, "function_call", None):
                        fc = part.function_call
                        yield None, [
                            SimpleNamespace(
                                id=uuid.uuid4().hex,
                                type="function",
                                function=SimpleNamespace(
                                    name=fc.name,
                                    arguments=json.dumps(
                                        dict(fc.args), ensure_ascii=False
                                    ),
                                ),
                            )
                        ]
                        return
'@.Replace("`r`n", "`n")
$CapturePatched = @'
                    if getattr(part, "function_call", None):
                        fc = part.function_call
                        kadence_call_id = uuid.uuid4().hex
                        self._kadence_tool_call_context[kadence_call_id] = {
                            "name": fc.name,
                            "thought_signature": getattr(
                                part, "thought_signature", None
                            ),
                        }
                        # Keep provider metadata bounded for a long-running
                        # backend without persisting any of it to disk.
                        while len(self._kadence_tool_call_context) > 64:
                            oldest_id = next(iter(self._kadence_tool_call_context))
                            self._kadence_tool_call_context.pop(oldest_id, None)
                        yield None, [
                            SimpleNamespace(
                                id=kadence_call_id,
                                type="function",
                                function=SimpleNamespace(
                                    name=fc.name,
                                    arguments=json.dumps(
                                        dict(fc.args), ensure_ascii=False
                                    ),
                                ),
                            )
                        ]
                        return
'@.Replace("`r`n", "`n")

if ($Text.Contains($CapturePatched)) {
    Write-Host "Kadence M5 Gemini thought-signature capture: already applied."
}
elseif ($Text.Contains($CaptureOriginal)) {
    $Text = $Text.Replace($CaptureOriginal, $CapturePatched)
    $Changed = $true
    Write-Host "Applied Kadence M5 Gemini thought-signature capture."
}
else {
    throw "Kadence M5 Gemini thought-signature capture guard failed; refusing to modify runtime."
}

if (-not $Text.Contains('self._kadence_tool_call_context = {}') -or
    -not $Text.Contains('kadence_part["thought_signature"] = kadence_signature') -or
    -not $Text.Contains('"function_response": {') -or
    -not $Text.Contains('"thought_signature": getattr(')) {
    throw "Kadence M5 Gemini tool-roundtrip post-patch verification failed."
}

if ($Changed) {
    [System.IO.File]::WriteAllText($GeminiProviderPath, $Text, $Utf8NoBom)
    Write-Host "Kadence M5 Gemini signed tool round-trip installed."
}
