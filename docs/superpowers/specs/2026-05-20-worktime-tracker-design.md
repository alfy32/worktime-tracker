# Work Time Tracker — Design Spec

**Date:** 2026-05-20  
**Status:** Approved

---

## Overview

A self-hosted Docker app that tracks work hours across two computers (Windows + Ubuntu) by reading OS-native login history. Runs on a local home server. A web UI shows daily/weekly summaries with "hours remaining" calculations. Manual entries handle holidays and office days.

---

## Goals

- **Primary:** Give a single, immediate answer to "can I stop working now, or do I need more hours today?"
- Automatically capture login/logout events from both computers without relying on fragile logout hooks
- Track a running hours bank (cumulative surplus/deficit against a 40h/week target) so overworked weeks reduce future targets and underworked weeks increase them
- Let the user mark sessions as non-work and add manual entries (holidays, office days)
- Accessible on the home network; optionally accessible remotely via Tailscale
- Look and feel like a polished, modern app

---

## Architecture

Three components:

1. **Sync agents** — scripts on each computer that read OS login history and POST it to the server
2. **Server** — FastAPI + SQLite in a Docker container on the home server
3. **Web UI** — served by the same container; vanilla JS + Tailwind CSS + Chart.js

---

## Sync Agents

### Strategy

Agents do not fire-and-forget. Each sync reads the last 30 days of OS login history and sends it all to the server. The server upserts — existing events are not duplicated. This means a missed logout hook or a restart is automatically corrected on the next login or scheduled sync.

### Triggers

Both computers run the sync agent:
- **At login** — catches up on any missed events since last session
- **Every 30 minutes while logged in** — keeps the current active session visible on the dashboard in real time

### Ubuntu

Uses the `last` command (reads `/var/log/wtmp`) which provides full login/logout history including logout times for clean logouts and crash/reboot markers for unclean ones.

- Script: Python or bash
- Login trigger: systemd user service (`~/.config/systemd/user/`)
- Schedule trigger: cron job every 30 minutes

### Windows

Uses PowerShell to query the Windows Security Event Log:
- Event ID 4624 = logon
- Event ID 4634 / 4647 = logoff
- Event ID 6006 / 1074 = shutdown/restart (used to infer logout time when no 4634 exists)

- Login trigger: Task Scheduler task on logon event
- Schedule trigger: Task Scheduler task on a 30-minute repeat
- Note: reading the Security Event Log requires the script to run with administrator privileges; the Task Scheduler tasks must be configured accordingly

### Sync Payload

Each sync POSTs an array of events to `POST /api/sync`:

```json
{
  "computer": "windows",
  "events": [
    { "timestamp": "2026-05-20T08:21:41", "action": "login" },
    { "timestamp": "2026-05-20T11:54:50", "action": "logout" }
  ]
}
```

The server upserts on `(computer, timestamp, action)` — re-syncing is always safe.

---

## Server

### Stack

- Python + FastAPI
- SQLite via SQLAlchemy
- Single Docker container
- `docker-compose.yml` with a named volume for the SQLite file (data survives restarts)

### Database

**`events` table**

| Column | Type | Notes |
|--------|------|-------|
| id | integer | primary key |
| computer | text | "windows" or "ubuntu" |
| timestamp | datetime | |
| action | text | "login" or "logout" |
| is_work | boolean | default true |

**`manual_entries` table**

| Column | Type | Notes |
|--------|------|-------|
| id | integer | primary key |
| date | date | |
| hours | decimal | default 8.0 |
| note | text | nullable — "New Years Day", "dentist", etc. |

### Session & Duration Calculation

A session is a login event paired with the next logout event from the same computer. Duration is calculated dynamically — never stored. If a login has no following logout, the session is considered active (end = now).

Break duration = gap between a logout and the next login on that computer.

### Hours Bank & Stop Time

**Running bank** = total work hours logged − (weekdays elapsed since tracking start × 8)

Positive = ahead, negative = behind. The bank carries forward indefinitely.

**Adjusted weekly target** = 40 − bank_at_start_of_this_week (capped at a sensible floor/ceiling, e.g. 20–60h, to avoid absurd values after an unusually long or short stretch)

**Today's stop time** = now + hours_remaining_today  
Where: hours_remaining_today = (adjusted_weekly_target − this_week_hours_so_far) ÷ remaining_weekdays_including_today

If the result is ≤ 0, the hero card shows "You're done for today."

Weekly target hours (default 40) and daily hours (default 8) are stored as user-configurable settings in the database.

### Overlap Merging

When calculating totals for a day or week, sessions across both computers are merged to avoid double-counting parallel login time:

1. Collect all `is_work = true` sessions for the period
2. Sort by start time
3. Walk and merge any overlapping intervals
4. Sum merged interval durations
5. Add `manual_entries.hours` for dates in the period

Per-computer hour totals are calculated separately (without merging) for display as a secondary stat.

### API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/sync` | Receive events from a sync agent |
| GET | `/api/summary/today` | Today's merged hours, per-computer split, sessions |
| GET | `/api/summary/week` | This week's daily breakdown |
| GET | `/api/summary/daily?days=60` | Daily totals for the last N days |
| GET | `/api/summary/weekly?weeks=26` | Weekly totals for the last N weeks |
| GET | `/api/events` | Paginated raw event log |
| PATCH | `/api/events/{id}` | Toggle is_work |
| POST | `/api/manual` | Add a manual entry |
| DELETE | `/api/manual/{id}` | Remove a manual entry |

---

## Web UI

### Pages

**Dashboard** (default)

The dashboard leads with one answer: *can I stop?*

- **Hero card (top, large):** "Stop at 4:47 PM · 1h 23m remaining" — or "You're done for today" if the target is met. Updates live as the 30-minute sync runs. Below the main message: running bank balance (e.g., "+2.5h banked overall") and this week's hours so far.
- **Status strip:** "Logged in on Ubuntu · 2h 14m" or "Logged out · last seen 3h ago" + per-computer split (Windows · Xh | Ubuntu · Xh)
- **This Week card:** adjusted weekly target (40h ± bank carried from prior weeks), hours worked so far, hours remaining, remaining weekdays. Weekend/night sessions count toward totals but don't add target days.
- **Recent bar chart:** last 10 days, merged daily totals, 8h reference line, color-coded (under = orange, met/over = teal), hoverable for computer breakdown

**Daily View**
- Bar chart: last 60 days
- Table below: date, total hours, sessions count, longest break — expandable row shows all sessions with is_work toggles

**Weekly View**
- Bar chart: last 26 weeks (6 months)
- Table: week, total hours, avg hours/day, delta from 40h

**Log**
- Paginated table: timestamp, computer, action, duration, is_work toggle
- Filter by computer and date range
- Add manual entry button (date picker, hours input defaulting to 8, optional note)

### Visual Style

- Dark theme: deep slate/gray background
- Accent color: teal/cyan for primary stats and active states; orange for under-target days
- Large prominent stat numbers on cards
- Chart.js for all charts, muted palette
- Tailwind CSS via CDN (no build step)
- Inter or system-ui font
- Fully responsive (readable on a phone)

---

## Data Import

The existing Google Sheet has data going back to 1/1/2026. Import will be handled as a separate step after the app is running:

- **Windows sync agent** will pull Event Log back to 1/1/2026 automatically on first sync
- **Ubuntu** will pull whatever `last` has available (machine is new, limited history)
- **Manual entries and edits** from the Google Sheet will be reconciled interactively — the user will walk through the sheet and add missing entries via the Log page UI

---

## Deployment

```
~/projects/personal/worktime-tracker/
  docker-compose.yml
  server/
    main.py
    models.py
    routers/
    static/        ← UI files served by FastAPI
  agents/
    ubuntu/
      sync.py
      worktime-sync.service   ← systemd unit
      worktime-sync.timer     ← systemd timer (30min)
    windows/
      sync.ps1
      install-tasks.ps1       ← registers Task Scheduler tasks
```

The Docker container exposes port 8000. On the home network, access at `http://homeserver:8000`. For remote access, install Tailscale on the home server.

---

## Out of Scope

- Authentication (home network only; Tailscale handles access control if remote)
- Multi-user support
- Mobile app (responsive web is sufficient)
- Automatic Google Sheet import (handled manually as a one-time migration)
