# Ubuntu Sync Agent — Design Spec

**Date:** 2026-05-20
**Status:** Approved

---

## Overview

A Python script that reads login/logout and lock/unlock history from `systemd-logind`'s journal and syncs it to the work time tracker server. Runs at login and every 5 minutes via systemd user units.

---

## Goals

- Automatically capture all events that affect "is the user actively working": login, logout, screen lock, screen unlock, shutdown, reboot
- Send the last 30 days of events on every sync — the server upserts, so re-syncing is always safe
- No external Python dependencies (stdlib only)
- Idempotent install: running `install.sh` again updates config and units without manual cleanup

---

## Architecture

Two files in `agents/ubuntu/`:

| File | Purpose |
|------|---------|
| `sync.py` | Reads journalctl, builds event payload, POSTs to server |
| `install.sh` | One-time (and re-runnable) setup: config, systemd units, initial sync |

Two systemd user units installed to `~/.config/systemd/user/`:

| Unit | Type | Trigger |
|------|------|---------|
| `worktime-sync.service` | oneshot | called by timer |
| `worktime-sync.timer` | timer | 1 min after login, then every 5 min |

Config file at `~/.config/worktime-tracker/config` (shell env format):

```
WORKTIME_SERVER_URL=http://192.168.x.x:8000
WORKTIME_COMPUTER_NAME=ubuntu
```

---

## Event Source & Mapping

**Source:** `journalctl -u systemd-logind --output json --since "30 days ago" --no-pager`

`systemd-logind` records all session lifecycle events in the journal. Only sessions "on seat seat0" are tracked — this naturally excludes SSH connections, which have no seat assignment.

| Journal message pattern | Server action |
|------------------------|---------------|
| `New session X of user Y on seat seat0.` | `login` |
| `Session X locked.` | `logout` |
| `Session X unlocked.` | `login` |
| `Session X logged out.` | `logout` |
| `Removed session X.` | `logout` |

Shutdown and reboot cause logind to remove active sessions, so `Removed session X.` covers those cases — no special handling needed.

A typical work day produces:
- morning login → `login`
- lunch lock → `logout`
- lunch unlock → `login`
- end of day logout → `logout`

This creates two sessions (morning and afternoon), correctly excluding the lunch break from the hours count.

---

## sync.py Internals

```
1. Load config from ~/.config/worktime-tracker/config (via os.environ after sourcing,
   or read file directly) — fall back to WORKTIME_SERVER_URL / WORKTIME_COMPUTER_NAME
   env vars, then error if not set.

2. Run: journalctl -u systemd-logind --output json --since "30 days ago" --no-pager
   Capture stdout. Parse each line as JSON.

3. Track graphical session IDs: when a message matches
   "New session X of user Y on seat seat0", record session ID X.

4. For each journal entry whose message matches a tracked session ID:
   - "New session X ... on seat seat0" → login at entry timestamp
   - "Session X locked."              → logout at entry timestamp
   - "Session X unlocked."            → login at entry timestamp
   - "Session X logged out."          → logout at entry timestamp
   - "Removed session X."             → logout at entry timestamp (only if X is tracked)

5. Convert __REALTIME_TIMESTAMP (microseconds since epoch) to ISO datetime string.
   Use local time (naive datetime, no timezone suffix) to match server expectations.

6. POST to {WORKTIME_SERVER_URL}/api/sync:
   {"computer": WORKTIME_COMPUTER_NAME, "events": [{"timestamp": "...", "action": "..."}]}

7. Print a one-line summary: "Synced N events (M inserted, K skipped)" using the
   server's response. On HTTP error, print the status code and body, exit 1.
```

---

## install.sh Behaviour

Running `install.sh` is safe at any time — it is fully idempotent.

Steps:
1. Detect the absolute path to `sync.py` from the script's own location (`$(dirname "$(realpath "$0")")/sync.py`)
2. Prompt for `WORKTIME_SERVER_URL` (show current value if config already exists)
3. Prompt for `WORKTIME_COMPUTER_NAME` (default: `$(hostname)`, show current value if set)
4. Write `~/.config/worktime-tracker/config` (creates directory if needed, overwrites if exists)
5. Write `~/.config/systemd/user/worktime-sync.service` (overwrites)
6. Write `~/.config/systemd/user/worktime-sync.timer` (overwrites)
7. `systemctl --user daemon-reload`
8. `systemctl --user enable worktime-sync.timer`
9. `systemctl --user restart worktime-sync.timer` (restarts even if already running, picks up new interval)
10. Run `python3 /path/to/sync.py` immediately for the first/updated sync
11. Print: "Installed. Next sync in ~1 min, then every 5 min. Logs: journalctl --user -u worktime-sync"

---

## Systemd Unit Files

**`worktime-sync.service`:**
```ini
[Unit]
Description=Work Time Tracker — sync login/lock events
After=network.target

[Service]
Type=oneshot
EnvironmentFile=%h/.config/worktime-tracker/config
ExecStart=/usr/bin/python3 /ABSOLUTE/PATH/TO/agents/ubuntu/sync.py
StandardOutput=journal
StandardError=journal
```

**`worktime-sync.timer`:**
```ini
[Unit]
Description=Work Time Tracker — sync timer

[Timer]
OnBootSec=1min
OnUnitActiveSec=5min
Unit=worktime-sync.service

[Install]
WantedBy=timers.target
```

The `ExecStart` path is written by `install.sh` using the detected absolute path — not a placeholder.

---

## Error Handling

- **Server unreachable:** `sync.py` exits 1 with an error message. The timer will retry at the next 5-minute interval. No retry loop in the script itself.
- **journalctl returns no output:** Treat as zero events — POST an empty events array (server handles gracefully via upsert).
- **Config file missing:** Exit 1 with a message pointing to `install.sh`.
- **HTTP non-200 response:** Print status + body, exit 1.

---

## Testing

No automated test suite. Manual verification after install:
1. `journalctl --user -u worktime-sync -f` — watch live
2. Lock and unlock the screen — confirm two new events appear in the server within 5 minutes
3. Check `http://{server}:8000` dashboard — session count and hours should update
4. Re-run `install.sh` with a different computer name — confirm config updates and next sync uses new name
