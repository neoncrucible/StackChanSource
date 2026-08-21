param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("gemini", "luna")]
    [string]$Profile,
    [string]$RuntimeRoot = (Join-Path $PSScriptRoot ".runtime")
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

New-Item -ItemType Directory -Force -Path $RuntimeRoot | Out-Null
$ProfilePath = Join-Path $RuntimeRoot "kadence-llm-profile.txt"
[System.IO.File]::WriteAllText(
    $ProfilePath,
    $Profile + [Environment]::NewLine,
    [System.Text.UTF8Encoding]::new($false)
)

Write-Host "Kadence pre-boot LLM profile set to: $Profile"
Write-Host "Profile file: $ProfilePath"
Write-Host "The selection is local-only and applies on the next server start."
