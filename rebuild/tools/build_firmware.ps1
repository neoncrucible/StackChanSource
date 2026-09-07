$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
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
