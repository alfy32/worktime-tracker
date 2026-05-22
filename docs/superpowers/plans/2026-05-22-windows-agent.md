# Windows Sync Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a PowerShell sync agent that reads login/logout/lock/unlock/shutdown events from the Windows Security and System Event Logs and POSTs them to the work time tracker server, triggered at logon, on screen unlock, and every 5 minutes.

**Architecture:** `sync.ps1` contains pure helper functions (event mapping, deduplication, config loading, HTTP POST) plus a `Get-RawEvents` query function and a `Main` entry point guarded from execution when dot-sourced for testing. `install.ps1` handles config prompts, Task Scheduler registration via XML, and the initial historical sync. Tests use Pester to unit-test all pure functions by dot-sourcing `sync.ps1`.

**Tech Stack:** PowerShell 5.1+, `Get-WinEvent` with XPath filtering (Security/System Event Log), `Register-ScheduledTask` with XML task definition, `Invoke-RestMethod`, Pester 5.x

---

## File Map

| File | Purpose |
|------|---------|
| `agents/windows/sync.ps1` | Config loading, event querying, mapping, dedup, HTTP POST, main entry point |
| `agents/windows/install.ps1` | Config prompts, Task Scheduler XML registration, initial sync |
| `tests/Test-WindowsSync.Tests.ps1` | Pester unit tests for all pure functions in sync.ps1 |

---

### Task 1: Scaffold sync.ps1 and test file

**Files:**
- Create: `agents/windows/sync.ps1`
- Create: `tests/Test-WindowsSync.Tests.ps1`

- [ ] **Step 1: Create `agents/windows/sync.ps1` with stubs and dot-source guard**

```powershell
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
```

- [ ] **Step 2: Create `tests/Test-WindowsSync.Tests.ps1` scaffold**

```powershell
BeforeAll {
    . (Join-Path $PSScriptRoot '../agents/windows/sync.ps1') -Since "1970-01-01"
}

Describe "Remove-ConsecutiveDuplicates" { }
Describe "ConvertTo-WorktimeEvents" { }
Describe "Get-Config" { }
Describe "Send-WorktimeEvents" { }
```

- [ ] **Step 3: Verify Pester is available and test scaffold runs**

Run on Windows (PowerShell) or Linux (pwsh):
```powershell
Invoke-Pester tests/Test-WindowsSync.Tests.ps1 -Output Detailed
```
Expected: 0 tests run, no errors. If Pester is missing:
```powershell
Install-Module Pester -Force -SkipPublisherCheck -Scope CurrentUser
```

- [ ] **Step 4: Commit**

```bash
git add agents/windows/sync.ps1 tests/Test-WindowsSync.Tests.ps1
git commit -m "feat: scaffold Windows sync agent and test file"
```

---

### Task 2: Remove-ConsecutiveDuplicates

**Files:**
- Modify: `agents/windows/sync.ps1`
- Modify: `tests/Test-WindowsSync.Tests.ps1`

- [ ] **Step 1: Write failing tests**

Replace the `Describe "Remove-ConsecutiveDuplicates"` block:

```powershell
Describe "Remove-ConsecutiveDuplicates" {
    It "returns empty for empty input" {
        Remove-ConsecutiveDuplicates @() | Should -BeNullOrEmpty
    }

    It "passes through a single event unchanged" {
        $events = @(@{ timestamp = "2026-05-22T09:00:00"; action = "login" })
        $result = Remove-ConsecutiveDuplicates $events
        $result.Count | Should -Be 1
        $result[0].action | Should -Be "login"
    }

    It "removes consecutive duplicate actions" {
        $events = @(
            @{ timestamp = "2026-05-22T09:00:00"; action = "login" },
            @{ timestamp = "2026-05-22T09:00:01"; action = "login" },
            @{ timestamp = "2026-05-22T17:00:00"; action = "logout" }
        )
        $result = Remove-ConsecutiveDuplicates $events
        $result.Count | Should -Be 2
        $result[0].action | Should -Be "login"
        $result[1].action | Should -Be "logout"
    }

    It "keeps non-consecutive same actions" {
        $events = @(
            @{ timestamp = "2026-05-22T09:00:00"; action = "login" },
            @{ timestamp = "2026-05-22T12:00:00"; action = "logout" },
            @{ timestamp = "2026-05-22T13:00:00"; action = "login" },
            @{ timestamp = "2026-05-22T17:00:00"; action = "logout" }
        )
        $result = Remove-ConsecutiveDuplicates $events
        $result.Count | Should -Be 4
    }

    It "keeps the first event in a consecutive run" {
        $events = @(
            @{ timestamp = "2026-05-22T09:00:00"; action = "logout" },
            @{ timestamp = "2026-05-22T09:00:01"; action = "logout" },
            @{ timestamp = "2026-05-22T09:00:02"; action = "logout" }
        )
        $result = Remove-ConsecutiveDuplicates $events
        $result.Count | Should -Be 1
        $result[0].timestamp | Should -Be "2026-05-22T09:00:00"
    }
}
```

- [ ] **Step 2: Run tests to verify they fail**

```powershell
Invoke-Pester tests/Test-WindowsSync.Tests.ps1 -Output Detailed
```
Expected: 5 tests fail.

- [ ] **Step 3: Implement Remove-ConsecutiveDuplicates**

Replace the stub in `sync.ps1`:

```powershell
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
```

- [ ] **Step 4: Run tests to verify they pass**

```powershell
Invoke-Pester tests/Test-WindowsSync.Tests.ps1 -Output Detailed
```
Expected: all 5 tests pass.

- [ ] **Step 5: Commit**

```bash
git add agents/windows/sync.ps1 tests/Test-WindowsSync.Tests.ps1
git commit -m "feat: implement Remove-ConsecutiveDuplicates with tests"
```

---

### Task 3: ConvertTo-WorktimeEvents

**Files:**
- Modify: `agents/windows/sync.ps1`
- Modify: `tests/Test-WindowsSync.Tests.ps1`

- [ ] **Step 1: Write failing tests**

Replace the `Describe "ConvertTo-WorktimeEvents"` block:

```powershell
Describe "ConvertTo-WorktimeEvents" {
    It "maps event 4624 to login" {
        $raw = @([PSCustomObject]@{ Id = 4624; TimeCreated = [datetime]"2026-05-22T09:00:00" })
        (ConvertTo-WorktimeEvents $raw)[0].action | Should -Be "login"
    }

    It "maps event 4801 to login" {
        $raw = @([PSCustomObject]@{ Id = 4801; TimeCreated = [datetime]"2026-05-22T09:00:00" })
        (ConvertTo-WorktimeEvents $raw)[0].action | Should -Be "login"
    }

    It "maps event 4634 to logout" {
        $raw = @([PSCustomObject]@{ Id = 4634; TimeCreated = [datetime]"2026-05-22T17:00:00" })
        (ConvertTo-WorktimeEvents $raw)[0].action | Should -Be "logout"
    }

    It "maps event 4647 to logout" {
        $raw = @([PSCustomObject]@{ Id = 4647; TimeCreated = [datetime]"2026-05-22T17:00:00" })
        (ConvertTo-WorktimeEvents $raw)[0].action | Should -Be "logout"
    }

    It "maps event 4800 to logout" {
        $raw = @([PSCustomObject]@{ Id = 4800; TimeCreated = [datetime]"2026-05-22T12:00:00" })
        (ConvertTo-WorktimeEvents $raw)[0].action | Should -Be "logout"
    }

    It "maps event 1074 to logout" {
        $raw = @([PSCustomObject]@{ Id = 1074; TimeCreated = [datetime]"2026-05-22T17:00:00" })
        (ConvertTo-WorktimeEvents $raw)[0].action | Should -Be "logout"
    }

    It "maps event 6006 to logout" {
        $raw = @([PSCustomObject]@{ Id = 6006; TimeCreated = [datetime]"2026-05-22T17:00:00" })
        (ConvertTo-WorktimeEvents $raw)[0].action | Should -Be "logout"
    }

    It "formats timestamp as yyyy-MM-ddTHH:mm:ss" {
        $raw = @([PSCustomObject]@{ Id = 4624; TimeCreated = [datetime]"2026-05-22T09:05:30" })
        (ConvertTo-WorktimeEvents $raw)[0].timestamp | Should -Be "2026-05-22T09:05:30"
    }

    It "sorts output by timestamp ascending" {
        $raw = @(
            [PSCustomObject]@{ Id = 4634; TimeCreated = [datetime]"2026-05-22T17:00:00" },
            [PSCustomObject]@{ Id = 4624; TimeCreated = [datetime]"2026-05-22T09:00:00" }
        )
        $result = ConvertTo-WorktimeEvents $raw
        $result[0].timestamp | Should -Be "2026-05-22T09:00:00"
        $result[1].timestamp | Should -Be "2026-05-22T17:00:00"
    }

    It "ignores unknown event IDs" {
        $raw = @([PSCustomObject]@{ Id = 9999; TimeCreated = [datetime]"2026-05-22T09:00:00" })
        ConvertTo-WorktimeEvents $raw | Should -BeNullOrEmpty
    }

    It "returns empty for empty input" {
        ConvertTo-WorktimeEvents @() | Should -BeNullOrEmpty
    }
}
```

- [ ] **Step 2: Run tests to verify they fail**

```powershell
Invoke-Pester tests/Test-WindowsSync.Tests.ps1 -Output Detailed
```
Expected: 11 tests fail.

- [ ] **Step 3: Implement ConvertTo-WorktimeEvents**

Replace the stub in `sync.ps1`:

```powershell
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
```

- [ ] **Step 4: Run tests to verify they pass**

```powershell
Invoke-Pester tests/Test-WindowsSync.Tests.ps1 -Output Detailed
```
Expected: all 11 tests pass.

- [ ] **Step 5: Commit**

```bash
git add agents/windows/sync.ps1 tests/Test-WindowsSync.Tests.ps1
git commit -m "feat: implement ConvertTo-WorktimeEvents with tests"
```

---

### Task 4: Get-Config

**Files:**
- Modify: `agents/windows/sync.ps1`
- Modify: `tests/Test-WindowsSync.Tests.ps1`

- [ ] **Step 1: Write failing tests**

Replace the `Describe "Get-Config"` block:

```powershell
Describe "Get-Config" {
    BeforeEach {
        Remove-Item Env:\WORKTIME_SERVER_URL   -ErrorAction SilentlyContinue
        Remove-Item Env:\WORKTIME_COMPUTER_NAME -ErrorAction SilentlyContinue
    }

    It "reads serverUrl and computerName from config file" {
        $tmp = Join-Path $TestDrive "config.json"
        '{"serverUrl":"http://192.168.0.125:8000","computerName":"windows"}' | Set-Content $tmp
        $result = Get-Config -ConfigPath $tmp
        $result.serverUrl    | Should -Be "http://192.168.0.125:8000"
        $result.computerName | Should -Be "windows"
    }

    It "strips trailing slash from serverUrl" {
        $tmp = Join-Path $TestDrive "config.json"
        '{"serverUrl":"http://192.168.0.125:8000/","computerName":"windows"}' | Set-Content $tmp
        $result = Get-Config -ConfigPath $tmp
        $result.serverUrl | Should -Be "http://192.168.0.125:8000"
    }

    It "reads from environment variables when config file is absent" {
        $env:WORKTIME_SERVER_URL    = "http://10.0.0.1:8000"
        $env:WORKTIME_COMPUTER_NAME = "mypc"
        $result = Get-Config -ConfigPath (Join-Path $TestDrive "missing.json")
        $result.serverUrl    | Should -Be "http://10.0.0.1:8000"
        $result.computerName | Should -Be "mypc"
    }

    It "throws when serverUrl is not set anywhere" {
        { Get-Config -ConfigPath (Join-Path $TestDrive "missing.json") } | Should -Throw
    }
}
```

- [ ] **Step 2: Run tests to verify they fail**

```powershell
Invoke-Pester tests/Test-WindowsSync.Tests.ps1 -Output Detailed
```
Expected: 4 tests fail.

- [ ] **Step 3: Implement Get-Config**

Replace the stub in `sync.ps1`:

```powershell
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
```

- [ ] **Step 4: Run tests to verify they pass**

```powershell
Invoke-Pester tests/Test-WindowsSync.Tests.ps1 -Output Detailed
```
Expected: all 4 tests pass.

- [ ] **Step 5: Commit**

```bash
git add agents/windows/sync.ps1 tests/Test-WindowsSync.Tests.ps1
git commit -m "feat: implement Get-Config with tests"
```

---

### Task 5: Send-WorktimeEvents

**Files:**
- Modify: `agents/windows/sync.ps1`
- Modify: `tests/Test-WindowsSync.Tests.ps1`

- [ ] **Step 1: Write failing tests**

Replace the `Describe "Send-WorktimeEvents"` block:

```powershell
Describe "Send-WorktimeEvents" {
    It "POSTs to /api/sync with correct payload" {
        Mock Invoke-RestMethod {
            $script:capturedUri  = $Uri
            $script:capturedBody = $Body | ConvertFrom-Json
            return [PSCustomObject]@{ inserted = 2; skipped = 0 }
        }
        $events = @(
            @{ timestamp = "2026-05-22T09:00:00"; action = "login" },
            @{ timestamp = "2026-05-22T17:00:00"; action = "logout" }
        )
        Send-WorktimeEvents -ServerUrl "http://server:8000" -ComputerName "mypc" -Events $events
        $script:capturedUri              | Should -Be "http://server:8000/api/sync"
        $script:capturedBody.computer    | Should -Be "mypc"
        $script:capturedBody.events.Count | Should -Be 2
    }

    It "returns inserted and skipped counts" {
        Mock Invoke-RestMethod { return [PSCustomObject]@{ inserted = 1; skipped = 3 } }
        $result = Send-WorktimeEvents -ServerUrl "http://server:8000" -ComputerName "mypc" `
            -Events @(@{ timestamp = "2026-05-22T09:00:00"; action = "login" })
        $result.inserted | Should -Be 1
        $result.skipped  | Should -Be 3
    }

    It "throws on connection error" {
        Mock Invoke-RestMethod { throw [System.Net.WebException]::new("Connection refused") }
        {
            Send-WorktimeEvents -ServerUrl "http://server:8000" -ComputerName "mypc" `
                -Events @(@{ timestamp = "2026-05-22T09:00:00"; action = "login" })
        } | Should -Throw
    }
}
```

- [ ] **Step 2: Run tests to verify they fail**

```powershell
Invoke-Pester tests/Test-WindowsSync.Tests.ps1 -Output Detailed
```
Expected: 3 tests fail.

- [ ] **Step 3: Implement Send-WorktimeEvents**

Replace the stub in `sync.ps1`:

```powershell
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
        -Uri    "$ServerUrl/api/sync" `
        -Method POST `
        -Body   $payload `
        -ContentType "application/json"
}
```

- [ ] **Step 4: Run tests to verify they pass**

```powershell
Invoke-Pester tests/Test-WindowsSync.Tests.ps1 -Output Detailed
```
Expected: all 3 tests pass.

- [ ] **Step 5: Commit**

```bash
git add agents/windows/sync.ps1 tests/Test-WindowsSync.Tests.ps1
git commit -m "feat: implement Send-WorktimeEvents with tests"
```

---

### Task 6: Get-RawEvents

**Files:**
- Modify: `agents/windows/sync.ps1`

No unit tests — `Get-WinEvent` is Windows-only. Verified via end-to-end test in Task 9.

- [ ] **Step 1: Implement Get-RawEvents**

Replace the stub in `sync.ps1`:

```powershell
function Get-RawEvents {
    param([datetime]$Since)

    $sinceUtc = $Since.ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ss.000Z")

    # 4624 filtered to interactive logon types only (2=interactive, 7=unlock, 10=remote)
    $securityLogonXPath = @"
*[System[TimeCreated[@SystemTime >= '$sinceUtc'] and EventID=4624] and
  EventData[Data[@Name='LogonType'] and (Data='2' or Data='7' or Data='10')]]
"@

    # lock, unlock, logoff events — no extra filtering needed
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
            if ($_.Exception.Message -notmatch 'No events were found') { throw }
        }
    }

    return $events
}
```

- [ ] **Step 2: Run all tests to confirm nothing regressed**

```powershell
Invoke-Pester tests/Test-WindowsSync.Tests.ps1 -Output Detailed
```
Expected: all tests still pass.

- [ ] **Step 3: Commit**

```bash
git add agents/windows/sync.ps1
git commit -m "feat: implement Get-RawEvents with XPath filtering"
```

---

### Task 7: Main function

**Files:**
- Modify: `agents/windows/sync.ps1`

- [ ] **Step 1: Implement Main**

Replace the stub in `sync.ps1`:

```powershell
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
```

- [ ] **Step 2: Run all tests to confirm nothing regressed**

```powershell
Invoke-Pester tests/Test-WindowsSync.Tests.ps1 -Output Detailed
```
Expected: all tests pass.

- [ ] **Step 3: Commit**

```bash
git add agents/windows/sync.ps1
git commit -m "feat: wire up Main function in sync.ps1"
```

---

### Task 8: install.ps1

**Files:**
- Create: `agents/windows/install.ps1`

- [ ] **Step 1: Create install.ps1**

```powershell
#Requires -Version 5.1
#Requires -RunAsAdministrator
<#
.SYNOPSIS
    Work Time Tracker — Windows agent installer.
    Sets up config, Task Scheduler task, and runs initial sync.
#>

$SCRIPT_DIR  = Split-Path -Parent (Resolve-Path $MyInvocation.MyCommand.Path)
$SYNC_PS1    = Join-Path $SCRIPT_DIR "sync.ps1"
$CONFIG_DIR  = Join-Path $env:APPDATA "worktime-tracker"
$CONFIG_PATH = Join-Path $CONFIG_DIR "config.json"
$TASK_NAME   = "WorktimeTracker-Sync"

# ── Load existing config for re-run UX ───────────────────────────
$currentUrl  = ""
$currentName = ""
if (Test-Path $CONFIG_PATH) {
    $existing    = Get-Content $CONFIG_PATH -Raw | ConvertFrom-Json
    $currentUrl  = $existing.serverUrl
    $currentName = $existing.computerName
}
$defaultName = if ($currentName) { $currentName } else { $env:COMPUTERNAME }

# ── Prompts ───────────────────────────────────────────────────────
Write-Host ""
Write-Host "Work Time Tracker — Windows Agent Installer"
Write-Host "────────────────────────────────────────────"
Write-Host ""

if ($currentUrl) {
    $inputUrl  = Read-Host "Server URL [$currentUrl]"
    $serverUrl = if ($inputUrl) { $inputUrl } else { $currentUrl }
} else {
    $serverUrl = Read-Host "Server URL (e.g. http://192.168.0.125:8000)"
}

$inputName    = Read-Host "Computer name [$defaultName]"
$computerName = if ($inputName) { $inputName } else { $defaultName }

# ── Validate ──────────────────────────────────────────────────────
if (-not $serverUrl) {
    Write-Error "Server URL cannot be empty."; exit 1
}
if ($computerName -match '\s') {
    Write-Error "Computer name cannot contain spaces."; exit 1
}

# ── Write config ─────────────────────────────────────────────────
New-Item -ItemType Directory -Force -Path $CONFIG_DIR | Out-Null
@{ serverUrl = $serverUrl.TrimEnd('/'); computerName = $computerName } |
    ConvertTo-Json | Set-Content -Path $CONFIG_PATH
Write-Host "Wrote $CONFIG_PATH"

# ── Register Task Scheduler task via XML ─────────────────────────
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

# ── Initial sync from Jan 1 of current year ───────────────────────
$yearStart = (Get-Date -Month 1 -Day 1 -Hour 0 -Minute 0 -Second 0).ToString("yyyy-MM-dd")
Write-Host ""
Write-Host "Running initial sync from $yearStart..."
& powershell.exe -NonInteractive -ExecutionPolicy Bypass -File "$SYNC_PS1" -Since $yearStart

Write-Host ""
Write-Host "Done."
Write-Host "To check task status: Get-ScheduledTask -TaskName $TASK_NAME | Get-ScheduledTaskInfo"
```

- [ ] **Step 2: Commit**

```bash
git add agents/windows/install.ps1
git commit -m "feat: add Windows agent installer with Task Scheduler XML registration"
```

---

### Task 9: Manual end-to-end verification on Windows

Run all steps on the Windows machine. No automated tests here.

- [ ] **Step 1: Install Pester and run the test suite on Windows**

Open PowerShell (does not need to be admin for this step):
```powershell
Install-Module Pester -Force -SkipPublisherCheck -Scope CurrentUser
cd C:\path\to\worktime-tracker
Invoke-Pester tests/Test-WindowsSync.Tests.ps1 -Output Detailed
```
Expected: all tests pass.

- [ ] **Step 2: Run the installer**

Open PowerShell **as Administrator**:
```powershell
Set-ExecutionPolicy Bypass -Scope Process
cd C:\path\to\worktime-tracker
.\agents\windows\install.ps1
```
Enter your server URL (`http://192.168.0.125:8000`) and computer name when prompted.
Expected: config written, task registered, initial sync completes with event count printed.

- [ ] **Step 3: Verify events appeared on the dashboard**

Open `http://192.168.0.125:8000` — Windows sessions from earlier this year should now appear.

Also check via API:
```powershell
(Invoke-RestMethod "http://192.168.0.125:8000/api/events").items |
    Where-Object { $_.computer -eq $env:COMPUTERNAME }
```
Expected: events with your Windows computer name.

- [ ] **Step 4: Verify the scheduled task exists with all three triggers**

```powershell
Get-ScheduledTask -TaskName WorktimeTracker-Sync | Select -ExpandProperty Triggers
```
Expected: three triggers — LogonTrigger, EventTrigger (EventID 4801), TimeTrigger (PT5M).

- [ ] **Step 5: Verify unlock trigger fires**

Lock the screen (Win+L) and unlock it. Wait ~5 seconds, then check `Get-ScheduledTaskInfo`:
```powershell
Get-ScheduledTask -TaskName WorktimeTracker-Sync | Get-ScheduledTaskInfo |
    Select LastRunTime, LastTaskResult
```
Expected: `LastRunTime` updated to just now, `LastTaskResult` = 0 (success).

- [ ] **Step 6: Final commit**

```bash
git add .
git commit -m "chore: verified Windows agent end-to-end"
git push
```
