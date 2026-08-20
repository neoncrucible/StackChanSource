param(
    [string]$OutputDirectory = (Join-Path $PSScriptRoot "dist")
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

if ($env:OS -ne "Windows_NT") {
    throw "The Kadence Control Surface EXE must be built on Windows."
}

Add-Type -AssemblyName System.Drawing

$Source = Join-Path $PSScriptRoot "control_surface\KadenceControlLauncher.cs"
if (-not (Test-Path $Source)) {
    throw "Launcher source not found: $Source"
}

$CscCandidates = @(
    (Join-Path $env:WINDIR "Microsoft.NET\Framework64\v4.0.30319\csc.exe"),
    (Join-Path $env:WINDIR "Microsoft.NET\Framework\v4.0.30319\csc.exe")
)
$Csc = $CscCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $Csc) {
    throw "The .NET Framework C# compiler (csc.exe) was not found."
}

New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
$OutputDirectory = (Resolve-Path $OutputDirectory).Path
$ExePath = Join-Path $OutputDirectory "Kadence Control Surface.exe"
$IconPath = Join-Path $OutputDirectory "KadenceEye.ico"

# Generate a small Kadence EYE icon using the same visual language as the UI.
$Bitmap = New-Object System.Drawing.Bitmap 256,256
$Graphics = [System.Drawing.Graphics]::FromImage($Bitmap)
$Graphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
$Graphics.Clear([System.Drawing.Color]::FromArgb(5,8,12))

$Cyan = [System.Drawing.Color]::FromArgb(0,217,255)
$Glow = [System.Drawing.Color]::FromArgb(55,0,217,255)
$Pen = New-Object System.Drawing.Pen($Cyan,10)
$RingPen = New-Object System.Drawing.Pen([System.Drawing.Color]::FromArgb(170,0,217,255),6)
$GlowBrush = New-Object System.Drawing.SolidBrush($Glow)
$PupilBrush = New-Object System.Drawing.SolidBrush($Cyan)
$Path = New-Object System.Drawing.Drawing2D.GraphicsPath

try {
    $Graphics.FillEllipse($GlowBrush,68,50,120,120)
    $Path.AddBezier(18,128,66,68,190,68,238,128)
    $Path.AddBezier(238,128,190,188,66,188,18,128)
    $Graphics.DrawPath($Pen,$Path)
    $Graphics.DrawEllipse($RingPen,82,82,92,92)
    $Graphics.DrawEllipse($RingPen,103,103,50,50)
    $Graphics.FillEllipse($PupilBrush,118,118,20,20)

    $Handle = $Bitmap.GetHicon()
    try {
        $Icon = [System.Drawing.Icon]::FromHandle($Handle)
        $Stream = [System.IO.File]::Create($IconPath)
        try { $Icon.Save($Stream) } finally { $Stream.Dispose() }
    }
    finally {
        Add-Type -TypeDefinition 'using System; using System.Runtime.InteropServices; public static class KadeNative { [DllImport("user32.dll")] public static extern bool DestroyIcon(IntPtr handle); }' -ErrorAction SilentlyContinue
        [KadeNative]::DestroyIcon($Handle) | Out-Null
    }
}
finally {
    $Path.Dispose()
    $Pen.Dispose()
    $RingPen.Dispose()
    $GlowBrush.Dispose()
    $PupilBrush.Dispose()
    $Graphics.Dispose()
    $Bitmap.Dispose()
}

$Arguments = @(
    "/nologo",
    "/target:winexe",
    "/optimize+",
    "/platform:anycpu",
    "/reference:System.dll",
    "/reference:System.Windows.Forms.dll",
    "/reference:System.Drawing.dll",
    ("/win32icon:{0}" -f $IconPath),
    ("/out:{0}" -f $ExePath),
    $Source
)

& $Csc @Arguments
if ($LASTEXITCODE -ne 0) {
    throw "Kadence Control Surface EXE build failed with exit code $LASTEXITCODE."
}

if (-not (Test-Path $ExePath)) {
    throw "Compiler reported success but the EXE was not created: $ExePath"
}

Write-Host ""
Write-Host "Kadence Control Surface EXE built successfully."
Write-Host "EXE: $ExePath"
Write-Host ""
Write-Host "You can move the EXE anywhere on this PC. It searches for the project automatically and also honours KADENCE_HOME."
