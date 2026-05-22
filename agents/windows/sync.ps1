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

function Get-Config { param([string]$ConfigPath = $CONFIG_PATH) }

function Get-RawEvents { param([datetime]$Since) }

function ConvertTo-WorktimeEvents { param($RawEvents) }

function Remove-ConsecutiveDuplicates { param($Events) }

function Send-WorktimeEvents {
    param([string]$ServerUrl, [string]$ComputerName, $Events)
}

function Main { param([string]$Since = "") }

if ($MyInvocation.InvocationName -ne '.') {
    Main -Since $Since
}
