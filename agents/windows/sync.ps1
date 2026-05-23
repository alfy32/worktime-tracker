#Requires -Version 5.1
<#
.SYNOPSIS
    Work Time Tracker - Windows sync agent.
    Reads login/logout/lock/unlock events from the Windows Event Log
    and POSTs them to the work time tracker server.
.PARAMETER Since
    DateTime string to query events from. Default: 7 days ago.
    Pass "2026-01-01" for the initial historical sync.
#>
param(
    [string]$Since = ""
)

$CONFIG_PATH      = Join-Path $env:APPDATA "worktime-tracker\config.json"
$LOGIN_EVENT_IDS  = @(4624, 4801)
$LOGOUT_EVENT_IDS = @(4634, 4647, 4800, 1074, 6006)

function Get-Config {
    param([string]$ConfigPath = $CONFIG_PATH)
    $serverUrl    = $null
    $computerName = $null

    if (Test-Path $ConfigPath) {
        $cfg = Get-Content $ConfigPath -Raw | ConvertFrom-Json
        $serverUrl    = $cfg.serverUrl
        $computerName = $cfg.computerName
    }

    if (-not $serverUrl)    { $serverUrl    = $env:WORKTIME_SERVER_URL }
    if (-not $computerName) { $computerName = $env:WORKTIME_COMPUTER_NAME }

    if (-not $serverUrl) {
        throw "WORKTIME_SERVER_URL not set. Run install.ps1 first."
    }
    if (-not $computerName) {
        $computerName = $env:COMPUTERNAME
    }

    return @{
        serverUrl    = $serverUrl.TrimEnd('/')
        computerName = $computerName
    }
}

function Get-RawEvents {
    param([datetime]$Since)

    $sinceUtc = $Since.ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ss.000Z")

    # 4624 filtered to interactive logon types only (2=interactive, 7=unlock, 10=remote)
    $securityLogonXPath = @"
*[System[TimeCreated[@SystemTime >= '$sinceUtc'] and EventID=4624] and
  EventData[Data[@Name='LogonType'] and (Data='2' or Data='7' or Data='10')]]
"@

    # lock, unlock, logoff events - no extra filtering needed
    $securityOtherXPath = @"
*[System[TimeCreated[@SystemTime >= '$sinceUtc'] and
  (EventID=4634 or EventID=4647 or EventID=4800 or EventID=4801)]]
"@

    $systemXPath = @"
*[System[TimeCreated[@SystemTime >= '$sinceUtc'] and
  (EventID=1074 or EventID=6006)]]
"@

    $events = @()
    foreach ($query in @(
        @{ Log = 'Security'; XPath = $securityLogonXPath },
        @{ Log = 'Security'; XPath = $securityOtherXPath },
        @{ Log = 'System';   XPath = $systemXPath }
    )) {
        try {
            $events += Get-WinEvent -LogName $query.Log -FilterXPath $query.XPath -ErrorAction Stop
        } catch {
            if ($_.FullyQualifiedErrorId -notmatch 'NoMatchingEventsFound') { throw }
        }
    }

    return $events
}

function ConvertTo-WorktimeEvents {
    param($RawEvents)
    if (-not $RawEvents -or $RawEvents.Count -eq 0) { return @() }

    $actionMap = @{}
    foreach ($id in $LOGIN_EVENT_IDS)  { $actionMap[$id] = "login" }
    foreach ($id in $LOGOUT_EVENT_IDS) { $actionMap[$id] = "logout" }

    $events = @()
    foreach ($raw in $RawEvents) {
        if ($actionMap.ContainsKey([int]$raw.Id)) {
            $events += @{
                timestamp = $raw.TimeCreated.ToString("yyyy-MM-ddTHH:mm:ss")
                action    = $actionMap[[int]$raw.Id]
            }
        }
    }

    return @($events | Sort-Object { $_.timestamp })
}

function Remove-ConsecutiveDuplicates {
    param($Events)
    if (-not $Events -or $Events.Count -eq 0) { return @() }
    if ($Events.Count -eq 1) { return @($Events[0]) }
    $result = @($Events[0])
    foreach ($event in $Events[1..($Events.Count - 1)]) {
        if ($event.action -ne $result[-1].action) {
            $result += $event
        }
    }
    return $result
}

function Send-WorktimeEvents {
    param(
        [string]$ServerUrl,
        [string]$ComputerName,
        $Events
    )
    $payload = @{
        computer = $ComputerName
        events   = @($Events)
    } | ConvertTo-Json -Depth 3

    return Invoke-RestMethod `
        -Uri         "$ServerUrl/api/sync" `
        -Method      POST `
        -Body        $payload `
        -ContentType "application/json" `
        -TimeoutSec  30
}

function Main {
    param([string]$Since = "")

    $cfg = Get-Config

    $sinceDate = if ($Since) {
        [datetime]::Parse($Since)
    } else {
        (Get-Date).AddDays(-7)
    }

    Write-Host "Querying events since $($sinceDate.ToString('yyyy-MM-dd HH:mm:ss'))..."
    $rawEvents = Get-RawEvents -Since $sinceDate
    $events    = ConvertTo-WorktimeEvents -RawEvents $rawEvents
    $events    = Remove-ConsecutiveDuplicates -Events $events

    if ($events.Count -eq 0) {
        Write-Host "No new events."
        return
    }

    $result = Send-WorktimeEvents `
        -ServerUrl    $cfg.serverUrl `
        -ComputerName $cfg.computerName `
        -Events       $events

    Write-Host "Synced $($events.Count) events ($($result.inserted) inserted, $($result.skipped) skipped)"
}

if ($MyInvocation.InvocationName -ne '.') {
    Main -Since $Since
}
