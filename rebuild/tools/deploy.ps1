param([string]$Port = 'COM4', [string]$Bundle = '', [switch]$BuildOnly, [switch]$HostOnly)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
if ($HostOnly -and ($Bundle -or $BuildOnly)) { throw 'HostOnly cannot be combined with firmware options.' }
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
Set-Location $root
$branch = (& git branch --show-current).Trim()
if ($LASTEXITCODE -ne 0 -or $branch -ne 'kadence/rebuild-kade') { throw 'Open the kadence/rebuild-kade checkout first.' }
$status = @(& git status --porcelain --untracked-files=no)
if ($LASTEXITCODE -ne 0) { throw 'Could not inspect checkout status.' }
if ($status.Count -gt 0) { throw 'Tracked local edits need review before updating. Nothing was deleted.' }
& git fetch origin kadence/rebuild-kade
if ($LASTEXITCODE -ne 0) { throw 'Could not fetch the real remote branch.' }
& git merge --ff-only origin/kadence/rebuild-kade
if ($LASTEXITCODE -ne 0) { throw 'Branch update needs review; no reset was performed.' }
$commit = (& git rev-parse HEAD).Trim()

# Resolve and check a supplied prebuilt candidate before changing the host install.
$firmware = ''
if ($Bundle) {
    if (!(Test-Path $Bundle)) { throw 'Firmware ZIP was not found at the supplied path.' }
    $firmware = Join-Path ([IO.Path]::GetTempPath()) ('kadence-' + [guid]::NewGuid().ToString('N'))
    Expand-Archive -LiteralPath $Bundle -DestinationPath $firmware
    $release = Get-Content -Raw (Join-Path $firmware 'RELEASE.json') | ConvertFrom-Json
    if ($release.source_commit -ne $commit) { throw 'Firmware and host commits differ. Use the matching source and bundle.' }
}
$hostPython = (& python -c 'import sys; print(sys.executable)').Trim()
if ($LASTEXITCODE -ne 0 -or !(Test-Path $hostPython)) { throw 'Could not resolve the host Python interpreter.' }
& $hostPython -m pip install -e "$root\rebuild[voice,vision,dev]"
if ($LASTEXITCODE -ne 0) { throw 'Host dependency install failed.' }
& $hostPython -m kcore.appliance --check
if ($LASTEXITCODE -ne 0) { throw 'Runtime setup check failed; firmware was not flashed.' }
& $hostPython "$root\rebuild\tools\phase_b_gate.py"
if ($LASTEXITCODE -ne 0) { throw 'Candidate host verification failed; firmware was not flashed.' }
& $hostPython "$root\rebuild\tools\phase_a3_voice_wire_gate.py"
if ($LASTEXITCODE -ne 0) { throw 'Audio ownership verification failed; firmware was not flashed.' }

if ($HostOnly) {
    Write-Host 'KADENCE_HOST READY. Run python -m kcore.appliance with your provider credentials in this terminal.'
    return
}
if (!$Bundle) {
    & "$PSScriptRoot\sdk_process.ps1" -Script "$PSScriptRoot\build_firmware.ps1"
    $firmware = "$root\rebuild\dist\Kadence-RC2-Firmware-$($commit.Substring(0,12))"
}
if (!$BuildOnly) {
    & "$PSScriptRoot\sdk_process.ps1" -Script (Join-Path $firmware 'flash.ps1') -ScriptArguments @('-Port', $Port)
}
Set-Location $root
Write-Host 'KADENCE_CANDIDATE READY. Run python -m kcore.appliance with your provider credentials in this terminal.'
