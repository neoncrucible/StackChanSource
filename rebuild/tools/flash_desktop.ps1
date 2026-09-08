param([string]$Port = 'COM4')
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$desktop = Get-Content -Raw (Join-Path $PSScriptRoot 'RELEASE.json') | ConvertFrom-Json
$firmware = Get-Content -Raw (Join-Path $PSScriptRoot 'Firmware\RELEASE.json') | ConvertFrom-Json
if ($desktop.source_commit -ne $firmware.source_commit) { throw 'Desktop and firmware commits differ. Extract one complete matching release.' }
if (Get-Process Kadence -ErrorAction SilentlyContinue) { throw 'Quit Kadence before flashing the robot.' }
& (Join-Path $PSScriptRoot 'Firmware\flash.ps1') -Port $Port
Write-Host 'KADENCE_DESKTOP READY. Restart the robot normally, then open Kadence.exe in this folder.'
