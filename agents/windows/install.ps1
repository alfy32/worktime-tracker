#Requires -Version 5.1
#Requires -RunAsAdministrator
<#
.SYNOPSIS
    Work Time Tracker - Windows agent installer.
    Sets up config, Task Scheduler task, and runs initial sync.
#>

$SCRIPT_DIR  = Split-Path -Parent (Resolve-Path $MyInvocation.MyCommand.Path)
$SYNC_PS1    = Join-Path $SCRIPT_DIR "sync.ps1"
$CONFIG_DIR  = Join-Path $env:APPDATA "worktime-tracker"
$CONFIG_PATH = Join-Path $CONFIG_DIR "config.json"
$TASK_NAME   = "WorktimeTracker-Sync"

# Load existing config for re-run UX
$currentUrl  = ""
$currentName = ""
if (Test-Path $CONFIG_PATH) {
    $existing    = Get-Content $CONFIG_PATH -Raw | ConvertFrom-Json
    $currentUrl  = $existing.serverUrl
    $currentName = $existing.computerName
}
$defaultName = if ($currentName) { $currentName } else { $env:COMPUTERNAME }

# Prompts
Write-Host ""
Write-Host "Work Time Tracker - Windows Agent Installer"
Write-Host "--------------------------------------------"
Write-Host ""

if ($currentUrl) {
    $inputUrl  = Read-Host "Server URL [$currentUrl]"
    $serverUrl = if ($inputUrl) { $inputUrl } else { $currentUrl }
} else {
    $serverUrl = Read-Host "Server URL (e.g. http://192.168.0.125:8000)"
}

$inputName    = Read-Host "Computer name [$defaultName]"
$computerName = if ($inputName) { $inputName } else { $defaultName }

# Validate
if (-not $serverUrl) {
    Write-Error "Server URL cannot be empty."; exit 1
}
if ($computerName -match '\s') {
    Write-Error "Computer name cannot contain spaces."; exit 1
}

# Write config
New-Item -ItemType Directory -Force -Path $CONFIG_DIR | Out-Null
@{ serverUrl = $serverUrl.TrimEnd('/'); computerName = $computerName } |
    ConvertTo-Json | Set-Content -Path $CONFIG_PATH -Encoding UTF8
Write-Host "Wrote $CONFIG_PATH"

# Register Task Scheduler task via XML
# XML allows all three trigger types: logon, event (4801 unlock), and 5-min repeat
$taskXml = @"
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>Work Time Tracker sync agent</Description>
  </RegistrationInfo>
  <Triggers>
    <LogonTrigger>
      <Enabled>true</Enabled>
    </LogonTrigger>
    <EventTrigger>
      <Enabled>true</Enabled>
      <Subscription>&lt;QueryList&gt;&lt;Query Id="0" Path="Security"&gt;&lt;Select Path="Security"&gt;*[System[EventID=4801]]&lt;/Select&gt;&lt;/Query&gt;&lt;/QueryList&gt;</Subscription>
    </EventTrigger>
    <TimeTrigger>
      <Enabled>true</Enabled>
      <StartBoundary>1970-01-01T00:00:00</StartBoundary>
      <Repetition>
        <Interval>PT5M</Interval>
        <StopAtDurationEnd>false</StopAtDurationEnd>
      </Repetition>
    </TimeTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>HighestAvailable</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <ExecutionTimeLimit>PT10M</ExecutionTimeLimit>
    <Enabled>true</Enabled>
  </Settings>
  <Actions>
    <Exec>
      <Command>powershell.exe</Command>
      <Arguments>-NonInteractive -ExecutionPolicy Bypass -File "$SYNC_PS1"</Arguments>
    </Exec>
  </Actions>
</Task>
"@

Unregister-ScheduledTask -TaskName $TASK_NAME -Confirm:$false -ErrorAction SilentlyContinue
Register-ScheduledTask -TaskName $TASK_NAME -Xml $taskXml -Force | Out-Null
Write-Host "Task '$TASK_NAME' registered (logon + unlock event + every 5 min)."

# Initial sync from Jan 1 of current year
$yearStart = (Get-Date -Month 1 -Day 1 -Hour 0 -Minute 0 -Second 0).ToString("yyyy-MM-dd")
Write-Host ""
Write-Host "Running initial sync from $yearStart..."
& powershell.exe -NonInteractive -ExecutionPolicy Bypass -File "$SYNC_PS1" -Since $yearStart

Write-Host ""
Write-Host "Done."
Write-Host "To check task status: Get-ScheduledTask -TaskName $TASK_NAME | Get-ScheduledTaskInfo"
