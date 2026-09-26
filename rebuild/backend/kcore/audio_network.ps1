param(
    [ValidateSet('Inspect','Request','Apply','Validate')][string]$Mode = 'Inspect',
    [Parameter(Mandatory=$true)][string]$ProgramBase64
)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object Text.UTF8Encoding($false)
$program = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($ProgramBase64))
if (-not [IO.Path]::IsPathRooted($program) -or -not (Test-Path -LiteralPath $program -PathType Leaf)) {
    throw 'The running application path is invalid.'
}
if ($Mode -eq 'Request') {
    # Only this helper runs elevated. The host/GUI retain normal user privileges.
    $quoted = $PSCommandPath.Replace("'", "''")
    $code = "& '$quoted' -Mode Apply -ProgramBase64 '$ProgramBase64'"
    $encoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($code))
    $child = Start-Process -FilePath (Join-Path $PSHOME 'powershell.exe') -Verb RunAs -Wait -PassThru `
        -ArgumentList "-NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -EncodedCommand $encoded"
    exit $child.ExitCode
}
if ($Mode -in @('Apply','Validate')) {
    $name = 'Kadence robot audio - private LAN'
    $group = 'Kadence audio'
    $rule = New-Object -ComObject HNetCfg.FWRule
    $rule.Name = $name
    $rule.Description = 'Robot audio to the currently installed Kadence. Private local subnet only.'
    $rule.Grouping = $group
    $rule.ApplicationName = $program
    $rule.Protocol = 6
    $rule.LocalPorts = '*'
    $rule.RemotePorts = '*'
    $rule.LocalAddresses = '*'
    $rule.RemoteAddresses = 'LocalSubnet'
    $rule.Profiles = 2
    $rule.InterfaceTypes = 'All'
    $rule.Direction = 1
    $rule.Action = 1
    $rule.EdgeTraversal = $false
    $rule.Enabled = $true
    if ($Mode -eq 'Validate') {
        # Construct and inspect a real COM rule without registering it. CI never
        # adds a firewall exception or invokes an administrator prompt.
        @{ interfaces=@(); rule_validated=$true; profiles=$rule.Profiles
           protocol=$rule.Protocol; remote=$rule.RemoteAddresses
           direction=$rule.Direction; action=$rule.Action; edge=$rule.EdgeTraversal
           program_matches=($rule.ApplicationName -ceq $program) } | ConvertTo-Json -Compress
        exit 0
    }
    if ([IO.Path]::GetFileName($program) -ine 'Kadence.exe') { throw 'Only the installed Kadence executable is supported.' }
    $policy = New-Object -ComObject HNetCfg.FwPolicy2
    $existing = @($policy.Rules | Where-Object { $_.Name -eq $name })
    foreach ($item in $existing) {
        if ($item.Grouping -ne $group) { throw 'An unrelated rule uses the Kadence rule name.' }
    }
    # Repoint only our own rule after a versioned install; no global setting or
    # other application's rule is changed. Existing block rules remain visible.
    foreach ($item in $existing) { $policy.Rules.Remove($name) }
    $policy.Rules.Add($rule)
    exit 0
}
$interfaces = @()
try {
    $adapters = @(Get-NetAdapter -ErrorAction Stop)
    foreach ($config in @(Get-NetIPConfiguration -All -ErrorAction Stop)) {
        $adapter = $adapters | Where-Object { $_.InterfaceIndex -eq $config.InterfaceIndex } | Select-Object -First 1
        if ($adapter.Status -ne 'Up') { continue }
        $category = switch ([string]$config.NetProfile.NetworkCategory) {
            'Private' { 'private' }; 'Public' { 'public' }; 'DomainAuthenticated' { 'domain' }; default { 'unknown' }
        }
        foreach ($address in @($config.IPv4Address)) {
            if (-not $address.IPAddress) { continue }
            $interfaces += @{
                address=[string]$address.IPAddress; physical=[bool]$adapter.HardwareInterface
                gateway=[bool]$config.IPv4DefaultGateway; profile=$category
                network=[string]$config.NetProfile.Name
            }
        }
    }
} catch { $interfaces = @() }
$rules = @(); $firewall = 'unknown'
try {
    $policy = New-Object -ComObject HNetCfg.FwPolicy2
    foreach ($rule in $policy.Rules) {
        if (-not $rule.Enabled -or $rule.Direction -ne 1 -or $rule.Protocol -notin @(6,256)) { continue }
        $application = [Environment]::ExpandEnvironmentVariables([string]$rule.ApplicationName).Trim('"')
        $exact = $application -ieq $program
        if (-not $exact -and $application -notin @('','*')) { continue }
        # Broad or app-specific blocks are candidates, not a claim that Windows
        # has evaluated every remote-address/service/IPsec/group-policy filter.
        if ($rule.Action -eq 0 -or $exact) {
            $rules += @{ action=$(if ($rule.Action -eq 0) {'block'} else {'allow'})
                application=$exact; profiles=[int]$rule.Profiles; ports=[string]$rule.LocalPorts }
        }
    }
    $firewall = 'checked'
} catch { $rules = @() }
@{ interfaces=@($interfaces | Select-Object -First 64); firewall=$firewall
   rules=@($rules | Select-Object -First 128) } | ConvertTo-Json -Depth 5 -Compress
