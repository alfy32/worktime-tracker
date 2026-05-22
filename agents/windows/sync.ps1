#Requires -Version 5.1
<#
.SYNOPSIS
    Work Time Tracker — Windows sync agent.
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
    $serverUrl    = $env:WORKTIME_SERVER_URL
    $computerName = $env:WORKTIME_COMPUTER_NAME

    if ((-not $serverUrl -or -not $computerName) -and (Test-Path $ConfigPath)) {
        $cfg = Get-Content $ConfigPath -Raw | ConvertFrom-Json
        if (-not $serverUrl)    { $serverUrl    = $cfg.serverUrl }
        if (-not $computerName) { $computerName = $cfg.computerName }
    }

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

function Get-RawEvents { param([datetime]$Since) }

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
    $result = @($Events[0])
    foreach ($event in $Events[1..($Events.Count - 1)]) {
        if ($event.action -ne $result[-1].action) {
            $result += $event
        }
    }
    return $result
}

function Send-WorktimeEvents {
    param([string]$ServerUrl, [string]$ComputerName, $Events)
}

function Main { param([string]$Since = "") }

if ($MyInvocation.InvocationName -ne '.') {
    Main -Since $Since
}
