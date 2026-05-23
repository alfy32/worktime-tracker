#Requires -Version 5.1
#Requires -RunAsAdministrator
<#
.SYNOPSIS
    Work Time Tracker - Windows agent installer.
    Sets up config and registers Task Scheduler tasks.
#>

$SCRIPT_DIR       = Split-Path -Parent (Resolve-Path $MyInvocation.MyCommand.Path)
$REPORT_PS1       = Join-Path $SCRIPT_DIR "report-event.ps1"
$CONFIG_DIR       = Join-Path $env:APPDATA "worktime-tracker"
$CONFIG_PATH      = Join-Path $CONFIG_DIR "config.json"
$TASK_LOGIN       = "WorktimeTracker-Login"
$TASK_LOGOUT      = "WorktimeTracker-Logout"

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
    $inputUrl  = Read-Host "Server URL [http://192.168.0.125:8000]"
    $serverUrl = if ($inputUrl) { $inputUrl } else { "http://192.168.0.125:8000" }
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

# --- Task 1: WorktimeTracker-Login ---
# Fires immediately on session unlock and logon via report-event.ps1 (fast, no event log reading)
$loginTaskXml = @"
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>Work Time Tracker - report login instantly on unlock/logon</Description>
  </RegistrationInfo>
  <Triggers>
    <SessionStateChangeTrigger>
      <Enabled>true</Enabled>
      <StateChange>SessionUnlock</StateChange>
    </SessionStateChangeTrigger>
    <LogonTrigger>
      <Enabled>true</Enabled>
    </LogonTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <ExecutionTimeLimit>PT1M</ExecutionTimeLimit>
    <Enabled>true</Enabled>
  </Settings>
  <Actions>
    <Exec>
      <Command>powershell.exe</Command>
      <Arguments>-NoProfile -WindowStyle Hidden -NonInteractive -ExecutionPolicy Bypass -File "$REPORT_PS1" -Action login</Arguments>
    </Exec>
  </Actions>
</Task>
"@

# --- Task 2: WorktimeTracker-Logout ---
# Fires immediately on session lock, user logoff (4647), and shutdown (1074)
# report-event.ps1 completes in well under a second, before shutdown can kill it
$logoutTaskXml = @"
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>Work Time Tracker - report logout instantly on lock/logoff/shutdown</Description>
  </RegistrationInfo>
  <Triggers>
    <SessionStateChangeTrigger>
      <Enabled>true</Enabled>
      <StateChange>SessionLock</StateChange>
    </SessionStateChangeTrigger>
    <EventTrigger>
      <Enabled>true</Enabled>
      <Subscription>&lt;QueryList&gt;&lt;Query Id="0" Path="Security"&gt;&lt;Select Path="Security"&gt;*[System[EventID=4647]]&lt;/Select&gt;&lt;/Query&gt;&lt;/QueryList&gt;</Subscription>
    </EventTrigger>
    <EventTrigger>
      <Enabled>true</Enabled>
      <Subscription>&lt;QueryList&gt;&lt;Query Id="0" Path="System"&gt;&lt;Select Path="System"&gt;*[System[EventID=1074]]&lt;/Select&gt;&lt;/Query&gt;&lt;/QueryList&gt;</Subscription>
    </EventTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <UserId>$env:USERDOMAIN\$env:USERNAME</UserId>
      <LogonType>S4U</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <ExecutionTimeLimit>PT1M</ExecutionTimeLimit>
    <Enabled>true</Enabled>
  </Settings>
  <Actions>
    <Exec>
      <Command>powershell.exe</Command>
      <Arguments>-NoProfile -WindowStyle Hidden -NonInteractive -ExecutionPolicy Bypass -File "$REPORT_PS1" -Action logout</Arguments>
    </Exec>
  </Actions>
</Task>
"@

foreach ($name in @($TASK_LOGIN, $TASK_LOGOUT, "WorktimeTracker-Sync")) {
    Unregister-ScheduledTask -TaskName $name -Confirm:$false -ErrorAction SilentlyContinue
}
Register-ScheduledTask -TaskName $TASK_LOGIN  -Xml $loginTaskXml  -Force | Out-Null
Register-ScheduledTask -TaskName $TASK_LOGOUT -Xml $logoutTaskXml -Force | Out-Null
Write-Host "Tasks registered:"
Write-Host "  $TASK_LOGIN  - fires instantly on unlock/logon"
Write-Host "  $TASK_LOGOUT - fires instantly on lock/logoff/shutdown"

Write-Host ""
Write-Host "Done."
Write-Host "To check task status:"
Write-Host "  Get-ScheduledTask -TaskName $TASK_LOGIN  | Get-ScheduledTaskInfo"
Write-Host "  Get-ScheduledTask -TaskName $TASK_LOGOUT | Get-ScheduledTaskInfo"
