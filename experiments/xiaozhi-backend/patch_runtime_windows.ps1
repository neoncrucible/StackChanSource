param(
    [Parameter(Mandatory = $true)][string]$RepoDir
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

# The pinned Xiaozhi snapshot uses google-generativeai==0.8.5 but passes a
# top-level `timeout=` argument to GenerativeModel.generate_content(). That SDK
# accepts per-request transport options through `request_options` instead.
# Keep the upstream commit pinned and patch only the ignored local runtime.
$GeminiProvider = Join-Path $RepoDir "main\xiaozhi-server\core\providers\llm\gemini\gemini.py"
if (-not (Test-Path $GeminiProvider)) {
    throw "Pinned Xiaozhi Gemini provider was not found: $GeminiProvider"
}

$Original = "            timeout=self.timeout,"
$Replacement = '            request_options={"timeout": self.timeout},'
$Text = Get-Content -Raw $GeminiProvider

if ($Text.Contains($Replacement)) {
    Write-Host "Xiaozhi Gemini compatibility patch: already applied."
    return
}

if (-not $Text.Contains($Original)) {
    throw "Gemini compatibility patch guard failed. Expected pinned timeout call was not found; refusing to modify runtime."
}

$Text = $Text.Replace($Original, $Replacement)
[System.IO.File]::WriteAllText(
    $GeminiProvider,
    $Text,
    [System.Text.UTF8Encoding]::new($false)
)

Write-Host "Applied Xiaozhi Gemini compatibility patch: timeout -> request_options.timeout"
