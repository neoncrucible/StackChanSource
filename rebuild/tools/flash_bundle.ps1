param([string]$Port = 'COM4')
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$bundle = $PSScriptRoot
$manifestPath = Join-Path $bundle 'flasher_args.json'
$releasePath = Join-Path $bundle 'RELEASE.json'
if (!(Test-Path $manifestPath) -or !(Test-Path $releasePath)) { throw 'Extract the complete firmware bundle before running flash.ps1.' }

# Check every packaged file before loading tools or opening the serial device.
foreach ($line in Get-Content (Join-Path $bundle 'SHA256SUMS')) {
    if ($line -notmatch '^([a-f0-9]{64})  (.+)$') { throw 'Invalid checksum manifest.' }
    $hash = $Matches[1]
    $relative = $Matches[2]
    $path = [IO.Path]::GetFullPath((Join-Path $bundle $relative))
    $prefix = [IO.Path]::GetFullPath($bundle).TrimEnd('\') + '\'
    if (!$path.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) { throw 'Unsafe bundle path.' }
    if (!(Test-Path $path) -or (Get-FileHash -Algorithm SHA256 $path).Hash.ToLowerInvariant() -ne $hash) { throw 'Firmware checksum verification failed.' }
}
$manifest = Get-Content -Raw $manifestPath | ConvertFrom-Json
$release = Get-Content -Raw $releasePath | ConvertFrom-Json
if ($manifest.extra_esptool_args.chip -ne 'esp32s3' -or $release.chip -ne 'esp32s3') { throw 'Wrong firmware target.' }
$allowedOffsets = @('0x0','0x8000','0xd000','0x10000')
$flashFiles = @()
foreach ($entry in $manifest.flash_files.PSObject.Properties) {
    if ($entry.Name -notin $allowedOffsets) { throw 'Unexpected flash offset; refusing to touch calibration or storage.' }
    $flashFiles += $entry.Name
    $flashFiles += (Join-Path $bundle $entry.Value)
}
if (@($manifest.flash_files.PSObject.Properties.Name | Where-Object { $_ -in @('0x0','0x8000','0x10000') }).Count -ne 3) { throw 'Incomplete flash bundle.' }
if (!(Get-Command idf.py -ErrorAction SilentlyContinue)) {
    $export = 'C:\Espressif\frameworks\esp-idf-v5.5.4\export.ps1'
    if (!(Test-Path $export)) { throw 'Open the ESP-IDF 5.5.4 terminal, then run this script again.' }
    . $export
}
$arguments = @('-m','esptool','--chip','esp32s3','--port',$Port,'--before','default_reset','--after','hard_reset','write_flash')
$arguments += @($manifest.write_flash_args)
$arguments += $flashFiles
& python @arguments
if ($LASTEXITCODE -ne 0) { throw 'Flash failed. Keep the full output for diagnosis.' }
Write-Host 'KADENCE_FLASH PASS. Start the matching host with kadence.'
