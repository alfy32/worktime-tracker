# Work Time Tracker — Project Overview

A self-hosted work hours tracker that reads OS login/logout history automatically and surfaces a single answer: when can you stop working today?

---

## The Problem It Solves

Manually tracking work hours is friction. The goal here is zero friction: log in to your computer in the morning, lock your screen at lunch, unlock when you're back, log out at the end of the day. The app captures all of that automatically and tells you how many hours you've worked and when you'll hit your target for the day.

It also carries a running "hours bank" across weeks — so if you worked extra hours one week, your target goes down the next week, and vice versa.

---

## Architecture

Three components:

```
[Ubuntu computer]                [Home server]
  sync.py           ──POST──▶   FastAPI + SQLite
  lock_listener.py              Docker container
                                     │
[Windows computer]          Web UI (port 8000)
  report-event.ps1  ──POST──▶   (same server)
```

1. **Sync agents** — scripts on each computer read OS login history and POST it to the server
2. **Server** — FastAPI + SQLite in a Docker container
3. **Web UI** — served by the same container; vanilla JS + Tailwind CSS + Chart.js

---

## How Tracking Works

### Event Model

Everything is an event: `login` or `logout`, with a timestamp and computer name. A session is a login/logout pair. Duration is calculated dynamically from pairs — never stored.

Sessions from multiple computers are overlap-merged when calculating daily totals, so parallel login time on two machines doesn't get double-counted.

If a login has no following logout, the session is treated as active (end = now).

### Ubuntu Agent

Two systemd user services run on the Ubuntu machine:

**`worktime-sync`** (oneshot timer, every 5 min)

Reads the last 30 days of `systemd-logind` journal entries and POSTs all events to the server. The server upserts on `(computer, timestamp, action)` — re-syncing is always safe and idempotent. This catches login/logout at the session level (boot, shutdown, graphical session start/end).

```
journalctl -u systemd-logind --output json --since "30 days ago"
```

Only "seat0" sessions are tracked — SSH connections have no seat assignment and are automatically excluded.

Both old-style (regex-parsed message text) and new-style (structured `CODE_FUNC`/`SESSION_ID`/`USER_ID` fields) systemd journal formats are supported.

**`worktime-lock-listener`** (persistent service)

Subscribes to `org.gnome.ScreenSaver.ActiveChanged` on the D-Bus session bus. Fires instantly on screen lock (Super+L or idle timeout) and unlock. Posts a logout on screen lock and a login on screen unlock. Also posts a final logout on SIGTERM so shutdowns are recorded cleanly before the process exits.

This complements the journal sync agent: `sync.py` owns session-level events (login at boot, logout at shutdown), `lock_listener.py` owns lock/unlock events in real time. They don't overlap, so no duplicate events.

### Windows Agent

Two PowerShell scripts run via Task Scheduler — no persistent background process, no Event Log reading.

**`report-event.ps1`** — called by both tasks. Posts a single event immediately and exits. Uses a 5-second timeout; silently fails if the network is down (the event is lost).

**Task Scheduler triggers (two tasks):**

`WorktimeTracker-Login` fires on:
- Session unlock (Win+L → unlock)
- User logon

`WorktimeTracker-Logout` fires on:
- Session lock (Win+L)
- Event ID 4647 (user-initiated logoff)
- Event ID 1074 (shutdown/restart)

The installer requires admin (to register Task Scheduler tasks). The registered tasks themselves run at `LeastPrivilege` — no elevated access at runtime.

**Known limitation:** On shutdown, Windows may kill the task before `report-event.ps1` completes — the logout event is lost. This is a Windows constraint; a service would be required to guarantee delivery.

**Config file:** `%APPDATA%\worktime-tracker\config.json`
```json
{
  "serverUrl": "http://192.168.0.125:8000",
  "computerName": "windows"
}
```

### Server-Side Deduplication

`POST /api/sync` upserts events using SQLite's `ON CONFLICT DO NOTHING` on `(computer, timestamp, action)`. Syncing the same event twice is always safe.

### Hours Bank

**Running bank** = total work hours logged − (weekdays elapsed since tracking start × 8)

A positive bank means you're ahead; negative means you're behind. The bank is carried forward indefinitely across weeks.

**Adjusted weekly target** = 40h − bank at start of this week (capped between 20h and 60h to prevent absurd values after an unusually long or short stretch)

**Today's stop time** = now + hours remaining today  
Where: hours remaining = (adjusted weekly target − hours worked so far this week) ÷ remaining weekdays including today

If the result is ≤ 0, the dashboard shows "You're done for today."

---

## Components

### Server (`server/`)

| File | Purpose |
|------|---------|
| `main.py` | FastAPI app, mounts routers and static files |
| `models.py` | SQLAlchemy models (`Event`, `ManualEntry`) |
| `schemas.py` | Pydantic request/response schemas |
| `database.py` | SQLite engine and session factory |
| `calculations.py` | Hours bank, stop time, overlap merging |
| `session_utils.py` | Login/logout pairing logic |
| `routers/sync.py` | `POST /api/sync` |
| `routers/sessions.py` | Session list and PATCH |
| `routers/summary.py` | Today, week, daily, weekly summaries |
| `routers/manual.py` | Manual entries |
| `static/` | Web UI (HTML + JS) |

### Ubuntu Agent (`agents/ubuntu/`)

| File | Purpose |
|------|---------|
| `sync.py` | Journal parser + HTTP POST; also the systemd service entrypoint |
| `lock_listener.py` | D-Bus lock/unlock listener; persistent systemd service |
| `install.sh` | Idempotent installer: config, systemd units, dep check, initial sync |

### Windows Agent (`agents/windows/`)

| File | Purpose |
|------|---------|
| `report-event.ps1` | Posts a single login or logout event instantly; called by both Task Scheduler tasks |
| `install.ps1` | Config prompts, Task Scheduler XML registration |

---

## Database Schema

### `events`

| Column | Type | Notes |
|--------|------|-------|
| id | integer | primary key |
| computer | text | e.g. `ubuntu`, `windows` |
| timestamp | datetime | local time, no timezone |
| action | text | `login` or `logout` |
| is_work | boolean | default true; false = excluded from totals |
| note | text | nullable — reason for non-work flag |

Unique constraint on `(computer, timestamp, action)`.

### `manual_entries`

| Column | Type | Notes |
|--------|------|-------|
| id | integer | primary key |
| date | date | |
| hours | decimal | default 8.0 |
| note | text | nullable — e.g. "New Year's Day", "dentist" |

---

## API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/sync` | Receive events from a sync agent |
| GET | `/api/summary/today` | Today's merged hours, per-computer split, sessions |
| GET | `/api/summary/week` | This week's daily breakdown |
| GET | `/api/summary/daily?days=60` | Daily totals for the last N days |
| GET | `/api/summary/weekly?weeks=26` | Weekly totals for the last N weeks |
| GET | `/api/events` | Paginated raw event log |
| PATCH | `/api/events/{id}` | Toggle `is_work` or add a note |
| POST | `/api/manual` | Add a manual entry |
| DELETE | `/api/manual/{id}` | Remove a manual entry |

---

## Web UI

### Dashboard

The primary view. Leads with one answer: when can you stop?

- **Hero card** — "Stop at 4:47 PM · 1h 23m remaining" or "You're done for today." Shows the running bank balance and this week's hours so far.
- **Status strip** — current login state per computer, per-computer hour split
- **This Week card** — adjusted weekly target, hours worked, hours remaining, remaining weekdays
- **Recent bar chart** — last 10 days, 8h reference line, orange for under-target days, teal for met/over

### Daily View

Bar chart of the last 60 days. Table below with date, total hours, session count, longest break. Expandable rows show individual sessions with is-work toggles.

### Weekly View

Bar chart of the last 26 weeks. Table with week, total hours, avg hours/day, delta from 40h.

### Log

Paginated event table. Filter by computer and date range. Add manual entries (date picker, hours, optional note).

---

## Deployment

The server runs in Docker. The `./data/` directory on the host holds the SQLite database:

```yaml
volumes:
  - ./data:/app/data
```

Adjust the host path in `docker-compose.yml` to wherever you want the database to live on your server.

**Port:** 8000 (HTTP). On the local network, access at `http://<server-ip>:8000`. For remote access, install Tailscale on the home server — no other auth is needed since it's single-user.

**Backups:** Copy `./data/worktime.db` on a schedule. A simple cron job works fine:
```bash
0 2 * * * cp /path/to/worktime-tracker/data/worktime.db /path/to/backups/worktime-$(date +\%Y\%m\%d).db
```

**Restart policy:** `restart: unless-stopped` in `docker-compose.yml` — the container starts automatically on server reboot.

---

## Out of Scope

- Authentication (home network + Tailscale is sufficient)
- Multi-user support
- Mobile app (the web UI is responsive)
