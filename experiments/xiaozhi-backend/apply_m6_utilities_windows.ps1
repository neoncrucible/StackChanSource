param(
    [string]$RuntimeRoot = (Join-Path $PSScriptRoot ".runtime")
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$RepoDir = Join-Path $RuntimeRoot "xiaozhi-esp32-server"
$ConnectionPath = Join-Path $RepoDir "main\xiaozhi-server\core\connection.py"
$UtilitySource = Join-Path $PSScriptRoot "kadence_utilities.py"
$UtilityTarget = Join-Path $RepoDir "main\xiaozhi-server\core\kadence_utilities.py"
$Utf8NoBom = [System.Text.UTF8Encoding]::new($false)

foreach ($RequiredPath in @($RepoDir, $ConnectionPath, $UtilitySource)) {
    if (-not (Test-Path $RequiredPath)) {
        throw "Kadence M6 required path was not found: $RequiredPath"
    }
}

$SourceText = [System.IO.File]::ReadAllText($UtilitySource, $Utf8NoBom)
$TargetText = if (Test-Path $UtilityTarget) {
    [System.IO.File]::ReadAllText($UtilityTarget, $Utf8NoBom)
} else {
    ""
}
if ($SourceText -ne $TargetText) {
    [System.IO.File]::WriteAllText($UtilityTarget, $SourceText, $Utf8NoBom)
    Write-Host "Installed Kadence M6 read-only utilities into local runtime."
} else {
    Write-Host "Kadence M6 read-only utilities already installed."
}

# M5 deliberately kept the handler provider-neutral and originally required only
# mode + logger. M6 web lookup needs the already-loaded local runtime config only
# to reuse Kadence's existing OpenAI credential; it does not expose config to the
# model or change tool authority.
$ConnText = [System.IO.File]::ReadAllText($ConnectionPath, $Utf8NoBom).Replace("`r`n", "`n")
$OldCall = @'
            self.func_handler = build_kadence_tool_handler(
                kadence_tool_mode,
                logger=self.logger,
            )
'@.Replace("`r`n", "`n")
$NewCall = @'
            self.func_handler = build_kadence_tool_handler(
                kadence_tool_mode,
                logger=self.logger,
                config=self.config,
            )
'@.Replace("`r`n", "`n")

if ($ConnText.Contains($NewCall)) {
    Write-Host "Kadence M6 tool config handoff: already applied."
}
elseif ($ConnText.Contains($OldCall)) {
    $ConnText = $ConnText.Replace($OldCall, $NewCall)
    [System.IO.File]::WriteAllText($ConnectionPath, $ConnText, $Utf8NoBom)
    Write-Host "Applied Kadence M6 tool config handoff."
}
else {
    throw "Kadence M6 config-handoff guard failed; refusing to modify runtime."
}

if (-not $ConnText.Contains('config=self.config,')) {
    throw "Kadence M6 config-handoff verification failed."
}
