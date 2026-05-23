# Windows Agent: Pure Event-Driven Design

## Summary

Remove the periodic log-reading reconciliation pass entirely. The agent becomes two Task Scheduler tasks that fire `report-event.ps1` instantly when events happen — no event log polling, no backfill.

## Motivation

The periodic `sync.ps1` reconciliation (every 5 min, reads Security/System event log) was unreliable — it didn't get events right. The instant event-firing path (`report-event.ps1`) worked well in prior use, matching the same trigger design that worked reliably in an older system (2019).

## What Changes

### Delete `agents/windows/sync.ps1`

Remove entirely. No log reading, no batch sync, no reconciliation.

### Update `agents/windows/install.ps1`

- Remove `$SYNC_PS1` and `$TASK_SYNC` variables
- Remove `WorktimeTracker-Sync` task XML and registration
- Remove initial historical sync call at the bottom
- Update status-check output to show only the two remaining tasks

## What Stays Unchanged

- `report-event.ps1` — fires instantly, posts a single event, silent-fails on network errors
- `WorktimeTracker-Login` task — SessionUnlock + LogonTrigger
- `WorktimeTracker-Logout` task — SessionLock + EventTrigger(4647) + EventTrigger(1074)

## Known Limitation

On shutdown, Windows may kill the task before `report-event.ps1` completes — the logout event is lost. This is a fundamental OS constraint and was present in the prior system too. The 5-second HTTP timeout in `report-event.ps1` minimizes the window. A Windows service would be required to guarantee delivery, which is out of scope.
