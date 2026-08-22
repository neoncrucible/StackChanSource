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

# M6 intentionally leaves the physically validated M5 ConnectionHandler call
# signature alone. An early M6 development build briefly added config=self.config;
# repair that obsolete local runtime shape if encountered, then verify the proven
# mode + logger call remains present.
$ConnText = [System.IO.File]::ReadAllText($ConnectionPath, $Utf8NoBom).Replace("`r`n", "`n")
$BaseCall = @'
            self.func_handler = build_kadence_tool_handler(
                kadence_tool_mode,
                logger=self.logger,
            )
'@.Replace("`r`n", "`n")
$ObsoleteCall = @'
            self.func_handler = build_kadence_tool_handler(
                kadence_tool_mode,
                logger=self.logger,
                config=self.config,
            )
'@.Replace("`r`n", "`n")

if ($ConnText.Contains($ObsoleteCall)) {
    $ConnText = $ConnText.Replace($ObsoleteCall, $BaseCall)
    [System.IO.File]::WriteAllText($ConnectionPath, $ConnText, $Utf8NoBom)
    Write-Host "Removed obsolete M6 config handoff; restored proven M5 handler wiring."
}
elseif ($ConnText.Contains($BaseCall)) {
    Write-Host "Kadence M6 handler wiring: proven M5 call preserved."
}
else {
    throw "Kadence M6 handler-wiring guard failed; refusing to modify runtime."
}

$VerifyText = [System.IO.File]::ReadAllText($ConnectionPath, $Utf8NoBom).Replace("`r`n", "`n")
if (-not $VerifyText.Contains($BaseCall) -or $VerifyText.Contains('config=self.config,')) {
    throw "Kadence M6 handler-wiring verification failed."
}
