param(
    [string]$RuntimeRoot = (Join-Path $PSScriptRoot ".runtime")
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$RepoDir = Join-Path $RuntimeRoot "xiaozhi-esp32-server"
$ConfigPath = Join-Path $RepoDir "main\xiaozhi-server\data\.config.yaml"
$PersonaPath = Join-Path $PSScriptRoot "persona\KADENCE_CANONICAL.md"
$PatchScript = Join-Path $PSScriptRoot "patch_runtime_luna_windows.ps1"
$Utf8NoBom = [System.Text.UTF8Encoding]::new($false)

if (-not (Test-Path $RepoDir)) {
    throw "Xiaozhi runtime not found. Run bootstrap_windows.ps1 first."
}
if (-not (Test-Path $ConfigPath)) {
    throw "Runtime config not found: $ConfigPath"
}
if (-not (Test-Path $PersonaPath)) {
    throw "Canonical Kadence persona not found: $PersonaPath"
}
if (-not (Test-Path $PatchScript)) {
    throw "Runtime compatibility patch script not found: $PatchScript"
}

# Run the active Luna-only guarded runtime repair first. This preserves the
# frozen Alpha 1 transport/M4 patches and ensures a repaired YAML file cannot
# overwrite the Alpha 2 persona after we inject it.
& $PatchScript -RepoDir $RepoDir

$ConfigText = [System.IO.File]::ReadAllText($ConfigPath, $Utf8NoBom)
$PersonaText = [System.IO.File]::ReadAllText($PersonaPath, $Utf8NoBom).Trim()

if ([string]::IsNullOrWhiteSpace($PersonaText)) {
    throw "Canonical Kadence persona is empty. Refusing to start Alpha 2."
}

$ConfigLines = [regex]::Split($ConfigText, "\r?\n")
$PersonaLines = [regex]::Split($PersonaText, "\r?\n")
$Output = New-Object 'System.Collections.Generic.List[string]'
$FoundPrompt = $false
$SkippingOldPrompt = $false

foreach ($Line in $ConfigLines) {
    if (-not $SkippingOldPrompt -and $Line -eq "prompt: |") {
        if ($FoundPrompt) {
            throw "Runtime config contains more than one top-level prompt block. Refusing to modify it."
        }

        $FoundPrompt = $true
        $SkippingOldPrompt = $true
        [void]$Output.Add("prompt: |")
        foreach ($PersonaLine in $PersonaLines) {
            [void]$Output.Add("  $PersonaLine")
        }
        [void]$Output.Add("")
        continue
    }

    if ($SkippingOldPrompt) {
        if ([string]::IsNullOrWhiteSpace($Line) -or $Line -match '^\s') {
            continue
        }
        $SkippingOldPrompt = $false
    }

    [void]$Output.Add($Line)
}

if (-not $FoundPrompt) {
    throw "Runtime config has no top-level 'prompt: |' block. Refusing to invent one."
}

$RenderedConfig = $Output -join "`r`n"
if ($RenderedConfig -ne $ConfigText) {
    [System.IO.File]::WriteAllText($ConfigPath, $RenderedConfig, $Utf8NoBom)
    Write-Host "Injected canonical Kadence persona into ignored runtime config."
}
else {
    Write-Host "Canonical Kadence persona already matches runtime config."
}

$PersonaHash = (Get-FileHash -Path $PersonaPath -Algorithm SHA256).Hash.ToLowerInvariant()
Write-Host "Kadence canonical identity: v2 / sha256 $PersonaHash"
Write-Host "Persona source: $PersonaPath"
