# Windows Sync Agent — Design Spec

**Date:** 2026-05-22
**Status:** Approved

---

## Overview

A PowerShell script that reads login/logout, lock/unlock, and shutdown/restart history from the Windows Security and System Event Logs and syncs it to the work time tracker server. Runs at login and every 5 minutes via Task Scheduler. No persistent background process.

---

## Goals

- Capture all events that affect "is the user actively working": login, logout, screen lock, screen unlock, shutdown, reboot
- Pull the last 7 days on every scheduled sync — the server upserts, so re-syncing is always safe
- Run an initial sync from January 1st of the current year to bootstrap historical data (captures whatever the Event Log still retains)
- No external dependencies beyond PowerShell and Windows built-ins
- Idempotent installer: running `install.ps1` again updates config and re-registers the task without manual cleanup

---

## Files

| File | Purpose |
|------|---------|
| `agents/windows/sync.ps1` | Reads Event Log, builds event payload, POSTs to server |
| `agents/windows/install.ps1` | Sets up config, Task Scheduler task, runs initial sync |

---

## Event Mapping

### Security Event Log

| Event ID | Logon Types | Action |
|----------|-------------|--------|
| 4624 | 2 (interactive), 7 (unlock), 10 (remote interactive) | `login` |
| 4634 | — | `logout` |
| 4647 | — | `logout` |
| 4800 | — | `logout` (workstation locked) |
| 4801 | — | `login` (workstation unlocked) |

Logon types 3 (network), 4 (batch), 5 (service), and others are excluded — only interactive sessions count.

### System Event Log

| Event ID | Source | Action |
|----------|--------|--------|
| 1074 | User32 | `logout` (shutdown/restart initiated) |
| 6006 | EventLog | `logout` (clean shutdown) |

### Deduplication

Consecutive same-action events are deduplicated during parsing — a workstation lock (4800) followed immediately by a shutdown (1074) produces only one `logout`. This prevents double-counting when multiple events fire in quick succession for the same state transition.

---

## sync.ps1 Internals

```
1. Load config from $env:APPDATA\worktime-tracker\config.json
   Fall back to environment variables WORKTIME_SERVER_URL and WORKTIME_COMPUTER_NAME.
   Exit with error if neither is set.

2. Accept optional -Since parameter (datetime string, default: 7 days ago).
   The installer passes (Jan 1 of current year) for the initial sync.

3. Query Security Event Log for event IDs 4624, 4634, 4647, 4800, 4801
   filtered to -StartTime $Since.

4. Query System Event Log for event IDs 1074, 6006
   filtered to -StartTime $Since.

5. Map each event to {timestamp, action}:
   - 4624: include only if LogonType in (2, 7, 10) → login
   - 4634/4647 → logout
   - 4800 → logout
   - 4801 → login
   - 1074/6006 → logout

6. Sort all events by timestamp ascending.
   Walk the list and drop any event where action == previous action (dedup).

7. POST to {serverUrl}/api/sync:
   {"computer": computerName, "events": [{timestamp, action}, ...]}
   Timestamps formatted as "yyyy-MM-ddTHH:mm:ss" (local time, no timezone).

8. Print: "Synced N events (M inserted, K skipped)" on success.
   On HTTP error, print status code and response body, exit 1.
   On network error, print error message, exit 1.
```

---

## install.ps1 Behaviour

Running `install.ps1` is safe at any time — fully idempotent.

Steps:
1. Load existing config if present (for re-run UX — show current values as defaults)
2. Prompt for `serverUrl` (show current value if set, no default otherwise)
3. Prompt for `computerName` (default: `$env:COMPUTERNAME`, show current value if set)
4. Validate: serverUrl non-empty, computerName non-empty and no spaces
5. Write `$env:APPDATA\worktime-tracker\config.json` (creates directory if needed)
6. Register Task Scheduler task `WorktimeTracker-Sync`:
   - Run as current user, elevated (highest privileges)
   - Trigger 1: At logon
   - Trigger 2: Repeat every 5 minutes indefinitely
   - Action: `powershell.exe -NonInteractive -ExecutionPolicy Bypass -File "<absolute path to sync.ps1>"`
   - If task already exists, unregister and re-register (idempotent)
7. Run initial sync: `sync.ps1 -Since (Jan 1 of current year)`
8. Print summary and log viewing instructions

---

## Task Scheduler Configuration

One task (`WorktimeTracker-Sync`) with three triggers:

```
Name:        WorktimeTracker-Sync
Run as:      Current user (admin account)
Privileges:  Highest (required to read Security Event Log)
Triggers:    At logon
             On Event: Log=Security, EventID=4801 (workstation unlocked)
             Every 5 minutes (repeat indefinitely, no expiry)
Action:      powershell.exe -NonInteractive -ExecutionPolicy Bypass -File "C:\...\sync.ps1"
```

The logon and unlock triggers ensure the dashboard updates immediately when the user sits down. The 5-minute repeat catches any gaps in between.

The absolute path to `sync.ps1` is resolved at install time from the installer's own location.

---

## Config File

Location: `$env:APPDATA\worktime-tracker\config.json`

```json
{
  "serverUrl": "http://192.168.0.125:8000",
  "computerName": "windows"
}
```

---

## Error Handling

- **Server unreachable:** Exit 1 with error message. Task Scheduler will retry at next 5-minute interval.
- **Event Log access denied:** Exit 1 with message pointing to admin requirement.
- **Config missing:** Exit 1 with message pointing to `install.ps1`.
- **HTTP non-200:** Print status code and body, exit 1.
- **No events found:** POST empty events array (server handles gracefully), print "No new events."

---

## Initial Bootstrap

The installer runs an initial sync with `-Since (Get-Date -Month 1 -Day 1 -Hour 0 -Minute 0 -Second 0)` to capture everything available in the Event Log back to January 1st of the current year. Older data may not be available depending on log size and retention — whatever exists will be captured.

Recommended before install: increase Security Event Log max size to retain more history going forward:
```powershell
wevtutil sl Security /ms:524288000  # 500 MB
```

---

## Checking Logs

After install, verify the task ran:
```powershell
Get-ScheduledTask -TaskName WorktimeTracker-Sync | Get-ScheduledTaskInfo
```

View task output (Task Scheduler doesn't capture stdout by default — redirect in the action if needed, or check the server dashboard directly).
