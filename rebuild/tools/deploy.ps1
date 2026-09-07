param([string]$Port = 'COM4', [string]$Bundle = '', [switch]$BuildOnly)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
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
& python -m pip install -e "$root\rebuild[voice,dev]"
if ($LASTEXITCODE -ne 0) { throw 'Host dependency install failed.' }
& python "$root\rebuild\tools\phase_b_gate.py"
if ($LASTEXITCODE -ne 0) { throw 'Candidate host verification failed; firmware was not flashed.' }
& python "$root\rebuild\tools\phase_a3_voice_wire_gate.py"
if ($LASTEXITCODE -ne 0) { throw 'Audio ownership verification failed; firmware was not flashed.' }

if (!$Bundle) {
    if (!(Get-Command idf.py -ErrorAction SilentlyContinue)) {
        $export = 'C:\Espressif\frameworks\esp-idf-v5.5.4\export.ps1'
        if (!(Test-Path $export)) { throw 'ESP-IDF 5.5.4 was not found at the expected path.' }
        . $export
    }
    Set-Location "$root\rebuild\firmware"
    & idf.py build
    if ($LASTEXITCODE -ne 0) { throw 'Firmware build failed; nothing was flashed.' }
    & python "$root\rebuild\tools\package_firmware.py"
    if ($LASTEXITCODE -ne 0) { throw 'Firmware packaging failed; nothing was flashed.' }
    $firmware = "$root\rebuild\dist\Kadence-RC1"
}
if (!$BuildOnly) { & (Join-Path $firmware 'flash.ps1') -Port $Port }
Set-Location $root
Write-Host 'KADENCE_CANDIDATE READY. Run kadence with your provider credentials in this terminal.'
