param(
    [string]$InstallRoot = (Join-Path $env:LOCALAPPDATA 'KadenceApp'),
    [string]$DesktopDirectory = [Environment]::GetFolderPath('Desktop'),
    [switch]$NoLaunch
)
$ErrorActionPreference = 'Stop'

# Versioned application files are separate from %LOCALAPPDATA%\Kadence data.
# Never terminate a running host or replace files underneath it.
if (Get-Process -Name Kadence -ErrorAction SilentlyContinue) {
    throw 'Quit Kadence completely, including its tray icon, then run this installer again.'
}
$release = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'RELEASE.json') -Raw | ConvertFrom-Json
if ($release.package_kind -ne 'desktop-host' -or $release.host_version -notmatch '^\d+\.\d+\.\d+$' -or $release.source_commit -notmatch '^[0-9a-f]{40}$') {
    throw 'Invalid Kadence desktop package.'
}
function Test-PackageFiles([string]$Root) {
    $lines = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'SHA256SUMS')
    foreach ($line in $lines) {
        if ($line -notmatch '^([0-9a-f]{64})  (.+)$') { throw 'Invalid package checksum entry.' }
        $expected = $Matches[1]
        $relative = $Matches[2]
        if ([IO.Path]::IsPathRooted($relative) -or $relative -match '(^|[/\\])\.\.([/\\]|$)' -or $relative.Contains(':')) {
            throw 'Invalid package file path.'
        }
        $file = Join-Path $Root $relative
        if (-not (Test-Path -LiteralPath $file -PathType Leaf)) { throw "Package file missing: $relative" }
        $stream = [IO.File]::OpenRead($file)
        $hasher = [Security.Cryptography.SHA256]::Create()
        try { $actual = [BitConverter]::ToString($hasher.ComputeHash($stream)).Replace('-', '').ToLowerInvariant() }
        finally { $stream.Dispose(); $hasher.Dispose() }
        if ($actual -ne $expected) { throw "Package checksum failed: $relative" }
    }
    if (-not (Test-Path -LiteralPath (Join-Path $Root 'Kadence.exe') -PathType Leaf)) { throw 'Kadence.exe is missing.' }
}
Test-PackageFiles $PSScriptRoot
$version = $release.host_version + '-' + $release.source_commit.Substring(0,12)
$versions = Join-Path $InstallRoot 'versions'
$destination = Join-Path $versions $version
New-Item -ItemType Directory -Path $versions -Force | Out-Null
$staging = Join-Path $versions ('staging-' + [guid]::NewGuid().ToString('N'))
try {
    if (Test-Path -LiteralPath $destination) {
        Test-PackageFiles $destination
    } else {
        New-Item -ItemType Directory -Path $staging | Out-Null
        Get-ChildItem -LiteralPath $PSScriptRoot -Force | Copy-Item -Destination $staging -Recurse -Force
        Test-PackageFiles $staging
        Move-Item -LiteralPath $staging -Destination $destination
    }
    New-Item -ItemType Directory -Path $DesktopDirectory -Force | Out-Null
    $shortcutPath = Join-Path $DesktopDirectory 'Kadence.lnk'
    $temporaryShortcut = Join-Path $DesktopDirectory ('Kadence-' + [guid]::NewGuid().ToString('N') + '.lnk')
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($temporaryShortcut)
    $shortcut.TargetPath = Join-Path $destination 'Kadence.exe'
    $shortcut.WorkingDirectory = $destination
    $shortcut.Description = 'Kadence Signal Console ' + $release.host_version
    $shortcut.Save()
    Move-Item -LiteralPath $temporaryShortcut -Destination $shortcutPath -Force
    Write-Host "Kadence $($release.host_version) installed. Use the Kadence desktop shortcut."
    Write-Host 'Your settings, credentials and database are unchanged. Previous application versions are retained.'
    if (-not $NoLaunch) { Start-Process -FilePath (Join-Path $destination 'Kadence.exe') -WorkingDirectory $destination }
} finally {
    if (Test-Path -LiteralPath $staging) { Remove-Item -LiteralPath $staging -Recurse -Force }
    if ($temporaryShortcut -and (Test-Path -LiteralPath $temporaryShortcut)) { Remove-Item -LiteralPath $temporaryShortcut -Force }
}
