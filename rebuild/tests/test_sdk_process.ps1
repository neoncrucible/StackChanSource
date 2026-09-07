$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$runner = Join-Path $PSScriptRoot '..\tools\sdk_process.ps1'
$fixture = Join-Path ([IO.Path]::GetTempPath()) ('kadence-sdk-test-' + [guid]::NewGuid().ToString('N') + '.ps1')
$originalPath = $env:PATH
try {
    foreach ($resultCode in @(0, 7)) {
        $content = @'
param([string]$Port)
if ($Port -ne 'COM4') { exit 9 }
$env:PATH = 'child-sdk-python-only'
exit RESULT_CODE
'@
        $content.Replace('RESULT_CODE', [string]$resultCode) | Set-Content -LiteralPath $fixture -Encoding UTF8
        $failed = $false
        try {
            & $runner -Script $fixture -ScriptArguments @('-Port', 'COM4')
        } catch {
            if ($resultCode -eq 0) { throw }
            if ($_.Exception.Message -notmatch 'exit code 7') { throw }
            $failed = $true
        }
        if ($failed -ne ($resultCode -ne 0)) { throw 'SDK failure was not propagated' }
        if ($env:PATH -cne $originalPath) { throw 'SDK process changed the host PATH' }
    }
    # The deliberate child exit 7 was verified above; leave the test successful.
    $global:LASTEXITCODE = 0
    Write-Host 'SDK_PROCESS PASS environment=preserved failure=propagated arguments=preserved'
} finally {
    Remove-Item -LiteralPath $fixture -ErrorAction SilentlyContinue
}
