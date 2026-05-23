# Windows Agent: Pure Event-Driven Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove `sync.ps1` and all references to it from `install.ps1`, leaving only the two instant event-firing tasks.

**Architecture:** Delete `sync.ps1` entirely. Trim `install.ps1` to register only `WorktimeTracker-Login` and `WorktimeTracker-Logout`. No other files change.

**Tech Stack:** PowerShell 5.1, Windows Task Scheduler XML

---

### Task 1: Delete sync.ps1

**Files:**
- Delete: `agents/windows/sync.ps1`

- [ ] **Step 1: Delete the file**

```bash
git rm agents/windows/sync.ps1
```

- [ ] **Step 2: Verify it's gone**

```bash
ls agents/windows/
```

Expected output:
```
install.ps1
report-event.ps1
```

- [ ] **Step 3: Commit**

```bash
git commit -m "remove: sync.ps1 - dropping log-reading reconciliation pass"
```

---

### Task 2: Remove sync references from install.ps1

**Files:**
- Modify: `agents/windows/install.ps1`

- [ ] **Step 1: Remove the `$SYNC_PS1` and `$TASK_SYNC` variable declarations (lines 10 and 16)**

Remove these two lines:
```powershell
$SYNC_PS1         = Join-Path $SCRIPT_DIR "sync.ps1"
```
```powershell
$TASK_SYNC        = "WorktimeTracker-Sync"
```

After the edit, the variable block at the top should look like:
```powershell
$SCRIPT_DIR       = Split-Path -Parent (Resolve-Path $MyInvocation.MyCommand.Path)
$REPORT_PS1       = Join-Path $SCRIPT_DIR "report-event.ps1"
$CONFIG_DIR       = Join-Path $env:APPDATA "worktime-tracker"
$CONFIG_PATH      = Join-Path $CONFIG_DIR "config.json"
$TASK_LOGIN       = "WorktimeTracker-Login"
$TASK_LOGOUT      = "WorktimeTracker-Logout"
```

- [ ] **Step 2: Remove the `$syncTaskXml` here-string (lines 143–183)**

Delete the entire block, from the comment through the closing `"@`:
```powershell
# --- Task 3: WorktimeTracker-Sync ---
# Runs every 5 minutes as a reconciliation pass - catches anything the instant tasks missed
# (e.g. network down at lock time, RDP sessions, historical gaps)
# Needs HighestAvailable to read the Security event log
$syncTaskXml = @"
<?xml version="1.0" encoding="UTF-16"?>
...
"@
```

- [ ] **Step 3: Update the task registration loop (lines 185–194)**

Replace:
```powershell
foreach ($name in @($TASK_LOGIN, $TASK_LOGOUT, $TASK_SYNC)) {
    Unregister-ScheduledTask -TaskName $name -Confirm:$false -ErrorAction SilentlyContinue
}
Register-ScheduledTask -TaskName $TASK_LOGIN  -Xml $loginTaskXml  -Force | Out-Null
Register-ScheduledTask -TaskName $TASK_LOGOUT -Xml $logoutTaskXml -Force | Out-Null
Register-ScheduledTask -TaskName $TASK_SYNC   -Xml $syncTaskXml   -Force | Out-Null
Write-Host "Tasks registered:"
Write-Host "  $TASK_LOGIN  - fires instantly on unlock/logon"
Write-Host "  $TASK_LOGOUT - fires instantly on lock/logoff/shutdown"
Write-Host "  $TASK_SYNC   - reconciliation pass every 5 min"
```

With:
```powershell
foreach ($name in @($TASK_LOGIN, $TASK_LOGOUT)) {
    Unregister-ScheduledTask -TaskName $name -Confirm:$false -ErrorAction SilentlyContinue
}
Register-ScheduledTask -TaskName $TASK_LOGIN  -Xml $loginTaskXml  -Force | Out-Null
Register-ScheduledTask -TaskName $TASK_LOGOUT -Xml $logoutTaskXml -Force | Out-Null
Write-Host "Tasks registered:"
Write-Host "  $TASK_LOGIN  - fires instantly on unlock/logon"
Write-Host "  $TASK_LOGOUT - fires instantly on lock/logoff/shutdown"
```

- [ ] **Step 4: Remove the initial sync block at the bottom**

Delete these lines:
```powershell
# Initial sync from Jan 1 of current year
$yearStart = (Get-Date -Month 1 -Day 1 -Hour 0 -Minute 0 -Second 0).ToString("yyyy-MM-dd")
Write-Host ""
Write-Host "Running initial sync from $yearStart..."
& powershell.exe -NonInteractive -ExecutionPolicy Bypass -File "$SYNC_PS1" -Since $yearStart
```

- [ ] **Step 5: Update the status-check output at the bottom**

Replace:
```powershell
Write-Host "To check task status:"
Write-Host "  Get-ScheduledTask -TaskName $TASK_LOGIN  | Get-ScheduledTaskInfo"
Write-Host "  Get-ScheduledTask -TaskName $TASK_LOGOUT | Get-ScheduledTaskInfo"
Write-Host "  Get-ScheduledTask -TaskName $TASK_SYNC   | Get-ScheduledTaskInfo"
```

With:
```powershell
Write-Host "To check task status:"
Write-Host "  Get-ScheduledTask -TaskName $TASK_LOGIN  | Get-ScheduledTaskInfo"
Write-Host "  Get-ScheduledTask -TaskName $TASK_LOGOUT | Get-ScheduledTaskInfo"
```

- [ ] **Step 6: Verify install.ps1 has no remaining references to sync**

```bash
grep -n "sync\|SYNC" agents/windows/install.ps1
```

Expected: no output.

- [ ] **Step 7: Commit**

```bash
git add agents/windows/install.ps1
git commit -m "feat: remove periodic sync task, agent is now pure event-driven"
```
