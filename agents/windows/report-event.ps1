#Requires -Version 5.1
<#
.SYNOPSIS
    Work Time Tracker - instant event reporter.
    Posts a single login or logout event immediately to the server.
    Designed to complete in well under a second for use in lock/shutdown triggers.
.PARAMETER Action
    "login" or "logout"
#>
param(
    [Parameter(Mandatory)]
    [ValidateSet('login', 'logout')]
    [string]$Action
)

$configPath = Join-Path $env:APPDATA 'worktime-tracker\config.json'
if (-not (Test-Path $configPath)) { exit 0 }

try {
    $cfg = Get-Content $configPath -Raw | ConvertFrom-Json
    if (-not $cfg.serverUrl -or -not $cfg.computerName) { exit 0 }

    $body = @{
        computer = $cfg.computerName
        events   = @(@{
            timestamp = (Get-Date).ToString('yyyy-MM-ddTHH:mm:ss')
            action    = $Action
        })
    } | ConvertTo-Json -Depth 3

    Invoke-RestMethod `
        -Uri         "$($cfg.serverUrl.TrimEnd('/'))/api/sync" `
        -Method      POST `
        -Body        $body `
        -ContentType 'application/json' `
        -TimeoutSec  5 | Out-Null
} catch {
    # Silent fail - if network is down, the event is lost
}
