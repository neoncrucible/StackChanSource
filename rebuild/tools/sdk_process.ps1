param(
    [Parameter(Mandatory = $true)][string]$Script,
    [string[]]$ScriptArguments = @()
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

# SDK export changes process environment variables. Keep those changes inside
# a child process so the installed host and subsequent startup use one Python.
& powershell.exe -NoLogo -NoProfile -File $Script @ScriptArguments
if ($LASTEXITCODE -ne 0) { throw "SDK task failed with exit code $LASTEXITCODE" }
