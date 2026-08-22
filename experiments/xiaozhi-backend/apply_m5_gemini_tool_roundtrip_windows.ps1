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

# google-generativeai==0.8.5 pins google-ai-generativelanguage==0.6.15, which
# predates Gemini 3 thought-signature support. Keep normal Gemini text chat on the
# proven SDK path, but use the same Gemini generateContent REST endpoint for tool
# mode so opaque thoughtSignature metadata can be preserved exactly without
# changing the frozen Python environment or adding a dependency.
$CacheOriginal = @'
        self.gen_cfg = GenerationConfig(
            max_output_tokens=2048,
        )
'@.Replace("`r`n", "`n")
$CachePatched = @'
        self.gen_cfg = GenerationConfig(
            max_output_tokens=2048,
        )

        # Provider-local metadata for Gemini function-call round-trips only.
        # Never log thought signatures and never persist them to disk.
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

$FunctionsOriginal = @'
    def response_with_functions(self, session_id, dialogue, functions=None):
        yield from self._generate(dialogue, self._build_tools(functions))

    def _generate(self, dialogue, tools):
'@.Replace("`r`n", "`n")
$FunctionsPatched = @'
    def response_with_functions(self, session_id, dialogue, functions=None):
        yield from self._generate_with_functions_rest(dialogue, functions)

    def _generate_with_functions_rest(self, dialogue, functions=None):
        role_map = {"assistant": "model", "user": "user"}
        contents = []

        for m in dialogue:
            r = m["role"]

            if r == "assistant" and "tool_calls" in m:
                parts = []
                for tc in m["tool_calls"]:
                    part = {
                        "functionCall": {
                            "name": tc["function"]["name"],
                            "args": json.loads(tc["function"]["arguments"]),
                        }
                    }
                    context = self._kadence_tool_call_context.get(
                        tc.get("id"), {}
                    )
                    signature = context.get("thought_signature")
                    if signature:
                        part["thoughtSignature"] = signature
                    parts.append(part)
                contents.append({"role": "model", "parts": parts})
                continue

            if r == "tool":
                context = self._kadence_tool_call_context.get(
                    m.get("tool_call_id"), {}
                )
                tool_name = context.get("name")
                raw_result = m.get("content", "")
                try:
                    result = json.loads(raw_result or "{}")
                except (json.JSONDecodeError, TypeError):
                    result = {"result": str(raw_result)}
                if not isinstance(result, dict):
                    result = {"result": result}

                if tool_name:
                    contents.append(
                        {
                            "role": "user",
                            "parts": [
                                {
                                    "functionResponse": {
                                        "name": tool_name,
                                        "response": result,
                                    }
                                }
                            ],
                        }
                    )
                else:
                    contents.append(
                        {
                            "role": "user",
                            "parts": [{"text": str(raw_result)}],
                        }
                    )
                continue

            contents.append(
                {
                    "role": role_map.get(r, "user"),
                    "parts": [{"text": str(m.get("content", ""))}],
                }
            )

        declarations = []
        for function in functions or []:
            declarations.append(
                {
                    "name": function["function"]["name"],
                    "description": function["function"]["description"],
                    "parameters": self._sanitize_kadence_tool_schema(
                        function["function"]["parameters"]
                    ),
                }
            )

        payload = {
            "contents": contents,
            "generationConfig": {"maxOutputTokens": 2048},
        }
        if declarations:
            payload["tools"] = [{"functionDeclarations": declarations}]

        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model_name}:generateContent"
        )
        response = requests.post(
            url,
            headers={
                "x-goog-api-key": self.api_key,
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = response.json()

        candidates = data.get("candidates") or []
        if not candidates:
            yield None, None
            return

        parts = candidates[0].get("content", {}).get("parts", [])
        for part in parts:
            function_call = part.get("functionCall")
            if function_call:
                call_id = uuid.uuid4().hex
                self._kadence_tool_call_context[call_id] = {
                    "name": function_call.get("name"),
                    "thought_signature": part.get("thoughtSignature"),
                }
                while len(self._kadence_tool_call_context) > 64:
                    oldest_id = next(iter(self._kadence_tool_call_context))
                    self._kadence_tool_call_context.pop(oldest_id, None)
                yield None, [
                    SimpleNamespace(
                        id=call_id,
                        type="function",
                        function=SimpleNamespace(
                            name=function_call.get("name"),
                            arguments=json.dumps(
                                function_call.get("args") or {},
                                ensure_ascii=False,
                            ),
                        ),
                    )
                ]
                return

            text = part.get("text")
            if text:
                yield text, None

        yield None, None

    def _generate(self, dialogue, tools):
'@.Replace("`r`n", "`n")

if ($Text.Contains($FunctionsPatched)) {
    Write-Host "Kadence M5 Gemini REST tool round-trip: already applied."
}
elseif ($Text.Contains($FunctionsOriginal)) {
    $Text = $Text.Replace($FunctionsOriginal, $FunctionsPatched)
    $Changed = $true
    Write-Host "Applied Kadence M5 Gemini REST tool round-trip with thought signatures."
}
else {
    throw "Kadence M5 Gemini REST tool-roundtrip guard failed; refusing to modify runtime."
}

if (-not $Text.Contains('self._kadence_tool_call_context = {}') -or
    -not $Text.Contains('yield from self._generate_with_functions_rest(dialogue, functions)') -or
    -not $Text.Contains('part["thoughtSignature"] = signature') -or
    -not $Text.Contains('"functionResponse": {') -or
    -not $Text.Contains('"x-goog-api-key": self.api_key')) {
    throw "Kadence M5 Gemini REST tool-roundtrip post-patch verification failed."
}

if ($Changed) {
    [System.IO.File]::WriteAllText($GeminiProviderPath, $Text, $Utf8NoBom)
    Write-Host "Kadence M5 Gemini signed REST tool round-trip installed."
}
