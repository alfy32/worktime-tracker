# Ubuntu Sync Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python sync agent for Ubuntu that reads login/logout/lock/unlock history from the systemd journal and POSTs it to the work time tracker server every 5 minutes.

**Architecture:** A single `sync.py` script with four pure functions (`parse_events`, `load_config`, `fetch_journal_lines`, `post_events`) plus a `main()` that wires them together. An `install.sh` bash script handles one-time (and re-runnable) systemd unit setup. `parse_events` is tested; the rest are thin wrappers around stdlib/subprocess that are verified manually.

**Tech Stack:** Python 3.12 (stdlib only — `json`, `re`, `subprocess`, `urllib.request`, `os`, `socket`), bash, systemd user units.

---

## File Map

| File | Purpose |
|------|---------|
| `agents/ubuntu/sync.py` | Journal parser, config loader, HTTP poster, main entry point |
| `agents/ubuntu/install.sh` | Idempotent installer: writes config, systemd units, starts timer |
| `tests/test_ubuntu_sync.py` | Unit tests for `parse_events` (and `load_config` via env vars) |

---

## Task 1: Journal Parser

**Files:**
- Create: `agents/ubuntu/sync.py`
- Create: `tests/test_ubuntu_sync.py`

- [ ] **Step 1: Create the agents/ubuntu directory**

```bash
mkdir -p ~/projects/personal/worktime-tracker/agents/ubuntu
```

- [ ] **Step 2: Write the failing tests**

Create `tests/test_ubuntu_sync.py`:

```python
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'agents', 'ubuntu'))
from sync import parse_events

BASE = 1_747_742_405_000_000  # arbitrary base timestamp, microseconds since epoch


def entry(ts_offset_seconds, message):
    return json.dumps({
        '__REALTIME_TIMESTAMP': str(BASE + ts_offset_seconds * 1_000_000),
        'MESSAGE': message,
    })


class TestParseEvents:
    def test_login_on_seat(self):
        lines = [entry(0, 'New session c1 of user alan on seat seat0.')]
        events = parse_events(lines)
        assert len(events) == 1
        assert events[0]['action'] == 'login'

    def test_ssh_session_ignored(self):
        # Sessions without "on seat" are SSH — must be excluded
        lines = [entry(0, 'New session c1 of user alan.')]
        assert parse_events(lines) == []

    def test_lock_produces_logout(self):
        lines = [
            entry(0,    'New session c1 of user alan on seat seat0.'),
            entry(3600, 'Session c1 locked.'),
        ]
        events = parse_events(lines)
        assert [e['action'] for e in events] == ['login', 'logout']

    def test_unlock_produces_login(self):
        lines = [
            entry(0, 'New session c1 of user alan on seat seat0.'),
            entry(1, 'Session c1 locked.'),
            entry(2, 'Session c1 unlocked.'),
        ]
        assert [e['action'] for e in events] == ['login', 'logout', 'login']

    def test_logged_out_produces_logout(self):
        lines = [
            entry(0, 'New session c1 of user alan on seat seat0.'),
            entry(1, 'Session c1 logged out.'),
        ]
        assert [e['action'] for e in parse_events(lines)] == ['login', 'logout']

    def test_removed_session_produces_logout(self):
        # Shutdown/reboot cause "Removed session X." — must count as logout
        lines = [
            entry(0, 'New session c1 of user alan on seat seat0.'),
            entry(1, 'Removed session c1.'),
        ]
        assert [e['action'] for e in parse_events(lines)] == ['login', 'logout']

    def test_lock_on_untracked_session_ignored(self):
        # Lock event for a session we never saw open — ignore it
        lines = [entry(0, 'Session c99 locked.')]
        assert parse_events(lines) == []

    def test_removed_on_untracked_session_ignored(self):
        lines = [entry(0, 'Removed session c99.')]
        assert parse_events(lines) == []

    def test_output_sorted_by_timestamp(self):
        # Feed events out of order — output must be sorted ascending
        lines = [
            entry(2, 'Session c1 locked.'),
            entry(0, 'New session c1 of user alan on seat seat0.'),
        ]
        events = parse_events(lines)
        assert events[0]['action'] == 'login'
        assert events[1]['action'] == 'logout'

    def test_timestamp_iso_format(self):
        lines = [entry(0, 'New session c1 of user alan on seat seat0.')]
        ts = parse_events(lines)[0]['timestamp']
        from datetime import datetime
        # Must parse without error and have no timezone suffix
        dt = datetime.strptime(ts, '%Y-%m-%dT%H:%M:%S')
        assert dt is not None

    def test_multiple_simultaneous_sessions(self):
        lines = [
            entry(0, 'New session c1 of user alan on seat seat0.'),
            entry(1, 'New session c2 of user alan on seat seat0.'),
            entry(2, 'Session c1 locked.'),
            entry(3, 'Session c2 logged out.'),
        ]
        events = parse_events(lines)
        assert len(events) == 4
        assert [e['action'] for e in events] == ['login', 'login', 'logout', 'logout']

    def test_empty_input(self):
        assert parse_events([]) == []

    def test_malformed_json_lines_skipped(self):
        lines = [
            '{not valid json}',
            entry(0, 'New session c1 of user alan on seat seat0.'),
        ]
        assert len(parse_events(lines)) == 1

    def test_missing_timestamp_skipped(self):
        lines = [json.dumps({'MESSAGE': 'New session c1 of user alan on seat seat0.'})]
        assert parse_events(lines) == []
```

- [ ] **Step 3: Run tests — confirm they fail**

```bash
cd ~/projects/personal/worktime-tracker
mise exec -- pytest tests/test_ubuntu_sync.py -v
```

Expected: `ModuleNotFoundError: No module named 'sync'` (file doesn't exist yet).

- [ ] **Step 4: Create `agents/ubuntu/sync.py` with `parse_events`**

```python
#!/usr/bin/env python3
"""Ubuntu sync agent — reads systemd-logind journal, POSTs events to work time tracker."""

import json
import os
import re
import socket
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime

_NEW_SESSION = re.compile(r'^New session (\S+) of user \S+ on seat seat0\.')
_LOCKED      = re.compile(r'^Session (\S+) locked\.')
_UNLOCKED    = re.compile(r'^Session (\S+) unlocked\.')
_LOGGED_OUT  = re.compile(r'^Session (\S+) logged out\.')
_REMOVED     = re.compile(r'^Removed session (\S+)\.')


def parse_events(lines):
    """Parse journalctl JSON lines into a list of event dicts.

    Args:
        lines: iterable of JSON strings from: journalctl -u systemd-logind --output json

    Returns:
        List of {'timestamp': 'YYYY-MM-DDTHH:MM:SS', 'action': 'login'|'logout'},
        sorted by timestamp ascending.
    """
    graphical_sessions = set()
    events = []

    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue

        ts_us = entry.get('__REALTIME_TIMESTAMP')
        if not ts_us:
            continue

        msg = entry.get('MESSAGE', '')
        dt = datetime.fromtimestamp(int(ts_us) / 1_000_000)
        iso = dt.strftime('%Y-%m-%dT%H:%M:%S')

        m = _NEW_SESSION.match(msg)
        if m:
            graphical_sessions.add(m.group(1))
            events.append({'timestamp': iso, 'action': 'login'})
            continue

        for pattern, action in (
            (_LOCKED,     'logout'),
            (_UNLOCKED,   'login'),
            (_LOGGED_OUT, 'logout'),
            (_REMOVED,    'logout'),
        ):
            m = pattern.match(msg)
            if m and m.group(1) in graphical_sessions:
                events.append({'timestamp': iso, 'action': action})
                break

    return sorted(events, key=lambda e: e['timestamp'])


def load_config():
    """Return (server_url, computer_name) from env vars or config file.

    Under systemd the EnvironmentFile= directive sets the env vars before
    this script runs. For manual invocation, source the config file first
    or set WORKTIME_SERVER_URL / WORKTIME_COMPUTER_NAME directly.
    """
    url = os.environ.get('WORKTIME_SERVER_URL', '').rstrip('/')
    name = os.environ.get('WORKTIME_COMPUTER_NAME', '')

    if not url or not name:
        config_path = os.path.expanduser('~/.config/worktime-tracker/config')
        if os.path.exists(config_path):
            with open(config_path) as f:
                for raw in f:
                    raw = raw.strip()
                    if raw.startswith('WORKTIME_SERVER_URL=') and not url:
                        url = raw.split('=', 1)[1].strip().rstrip('/')
                    elif raw.startswith('WORKTIME_COMPUTER_NAME=') and not name:
                        name = raw.split('=', 1)[1].strip()

    if not url:
        print('Error: WORKTIME_SERVER_URL not set. Run agents/ubuntu/install.sh first.',
              file=sys.stderr)
        sys.exit(1)

    if not name:
        name = socket.gethostname()

    return url, name


def fetch_journal_lines(since='30 days ago'):
    """Run journalctl and return stdout as a list of lines."""
    result = subprocess.run(
        ['journalctl', '-u', 'systemd-logind',
         '--output', 'json', '--since', since, '--no-pager'],
        capture_output=True, text=True,
    )
    return result.stdout.splitlines()


def post_events(server_url, computer_name, events):
    """POST events to /api/sync. Returns (inserted, skipped) counts."""
    payload = json.dumps({'computer': computer_name, 'events': events}).encode()
    req = urllib.request.Request(
        server_url + '/api/sync',
        data=payload,
        headers={'Content-Type': 'application/json'},
        method='POST',
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = json.loads(resp.read())
            return body.get('inserted', 0), body.get('skipped', 0)
    except urllib.error.HTTPError as e:
        print(f'HTTP {e.code}: {e.read().decode()}', file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f'Connection error: {e.reason}', file=sys.stderr)
        sys.exit(1)


def main():
    server_url, computer_name = load_config()
    lines = fetch_journal_lines()
    events = parse_events(lines)
    if not events:
        print('No events found in journal.')
        return
    inserted, skipped = post_events(server_url, computer_name, events)
    print(f'Synced {len(events)} events ({inserted} inserted, {skipped} skipped)')


if __name__ == '__main__':
    main()
```

- [ ] **Step 5: Run tests — confirm they pass**

```bash
cd ~/projects/personal/worktime-tracker
mise exec -- pytest tests/test_ubuntu_sync.py -v
```

Expected: all 14 tests PASS.

- [ ] **Step 6: Fix the variable name bug in the test file**

In `test_unlock_produces_login`, `events` is referenced before assignment. Fix it:

```python
    def test_unlock_produces_login(self):
        lines = [
            entry(0, 'New session c1 of user alan on seat seat0.'),
            entry(1, 'Session c1 locked.'),
            entry(2, 'Session c1 unlocked.'),
        ]
        events = parse_events(lines)
        assert [e['action'] for e in events] == ['login', 'logout', 'login']
```

Re-run:

```bash
mise exec -- pytest tests/test_ubuntu_sync.py -v
```

Expected: all 14 tests PASS.

- [ ] **Step 7: Commit**

```bash
cd ~/projects/personal/worktime-tracker
git add agents/ubuntu/sync.py tests/test_ubuntu_sync.py
git commit -m "feat: ubuntu sync agent — journal parser with tests"
```

---

## Task 2: Config Loader Tests

**Files:**
- Modify: `tests/test_ubuntu_sync.py`

The `load_config` function reads from env vars (falling back to the config file). We test it via env vars only — no filesystem setup needed.

- [ ] **Step 1: Add `load_config` tests to `tests/test_ubuntu_sync.py`**

Append to the existing file:

```python
import importlib
import unittest.mock as mock


class TestLoadConfig:
    def test_reads_from_env_vars(self):
        with mock.patch.dict(os.environ, {
            'WORKTIME_SERVER_URL': 'http://192.168.1.10:8000',
            'WORKTIME_COMPUTER_NAME': 'mydesktop',
        }):
            from sync import load_config
            url, name = load_config()
        assert url == 'http://192.168.1.10:8000'
        assert name == 'mydesktop'

    def test_trailing_slash_stripped_from_url(self):
        with mock.patch.dict(os.environ, {
            'WORKTIME_SERVER_URL': 'http://192.168.1.10:8000/',
            'WORKTIME_COMPUTER_NAME': 'mydesktop',
        }):
            from sync import load_config
            url, _ = load_config()
        assert url == 'http://192.168.1.10:8000'

    def test_missing_url_exits(self):
        env = {k: v for k, v in os.environ.items()
               if k not in ('WORKTIME_SERVER_URL', 'WORKTIME_COMPUTER_NAME')}
        # Ensure no config file is found by patching expanduser
        with mock.patch.dict(os.environ, env, clear=True), \
             mock.patch('os.path.exists', return_value=False):
            import pytest
            from sync import load_config
            with pytest.raises(SystemExit):
                load_config()

    def test_hostname_used_when_name_not_set(self):
        with mock.patch.dict(os.environ, {
            'WORKTIME_SERVER_URL': 'http://192.168.1.10:8000',
        }), mock.patch.dict(os.environ, {}, clear=False):
            # Remove computer name if present
            env_copy = dict(os.environ)
            env_copy.pop('WORKTIME_COMPUTER_NAME', None)
            with mock.patch.dict(os.environ, env_copy, clear=True), \
                 mock.patch('os.path.exists', return_value=False), \
                 mock.patch('socket.gethostname', return_value='testhost'):
                from sync import load_config
                _, name = load_config()
        assert name == 'testhost'
```

- [ ] **Step 2: Run the new tests**

```bash
cd ~/projects/personal/worktime-tracker
mise exec -- pytest tests/test_ubuntu_sync.py::TestLoadConfig -v
```

Expected: all 4 tests PASS.

- [ ] **Step 3: Run the full test suite to check for regressions**

```bash
cd ~/projects/personal/worktime-tracker
mise exec -- pytest -v
```

Expected: all tests PASS (existing server tests + new ubuntu agent tests).

- [ ] **Step 4: Commit**

```bash
cd ~/projects/personal/worktime-tracker
git add tests/test_ubuntu_sync.py
git commit -m "test: load_config tests for ubuntu sync agent"
```

---

## Task 3: install.sh

**Files:**
- Create: `agents/ubuntu/install.sh`

- [ ] **Step 1: Create `agents/ubuntu/install.sh`**

```bash
#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$(realpath "$0")")" && pwd)"
SYNC_PY="$SCRIPT_DIR/sync.py"
CONFIG_DIR="$HOME/.config/worktime-tracker"
CONFIG_FILE="$CONFIG_DIR/config"
SYSTEMD_DIR="$HOME/.config/systemd/user"

# ── Load existing values for re-run UX ──────────────────────────
current_url=""
current_name=""
if [[ -f "$CONFIG_FILE" ]]; then
  current_url=$(grep '^WORKTIME_SERVER_URL=' "$CONFIG_FILE" | cut -d= -f2- || true)
  current_name=$(grep '^WORKTIME_COMPUTER_NAME=' "$CONFIG_FILE" | cut -d= -f2- || true)
fi
default_name="${current_name:-$(hostname)}"

# ── Prompts ──────────────────────────────────────────────────────
echo ""
echo "Work Time Tracker — Ubuntu Agent Installer"
echo "─────────────────────────────────────────"
echo ""

if [[ -n "$current_url" ]]; then
  read -rp "Server URL [$current_url]: " input_url
  SERVER_URL="${input_url:-$current_url}"
else
  read -rp "Server URL (e.g. http://192.168.1.10:8000): " SERVER_URL
fi

read -rp "Computer name [$default_name]: " input_name
COMPUTER_NAME="${input_name:-$default_name}"

# ── Write config ─────────────────────────────────────────────────
mkdir -p "$CONFIG_DIR"
cat > "$CONFIG_FILE" <<EOF
WORKTIME_SERVER_URL=$SERVER_URL
WORKTIME_COMPUTER_NAME=$COMPUTER_NAME
EOF
echo "Wrote $CONFIG_FILE"

# ── Write systemd units ──────────────────────────────────────────
mkdir -p "$SYSTEMD_DIR"

cat > "$SYSTEMD_DIR/worktime-sync.service" <<EOF
[Unit]
Description=Work Time Tracker — sync login/lock events
After=network.target

[Service]
Type=oneshot
EnvironmentFile=%h/.config/worktime-tracker/config
ExecStart=/usr/bin/python3 $SYNC_PY
StandardOutput=journal
StandardError=journal
EOF

cat > "$SYSTEMD_DIR/worktime-sync.timer" <<EOF
[Unit]
Description=Work Time Tracker — sync timer

[Timer]
OnBootSec=1min
OnUnitActiveSec=5min
Unit=worktime-sync.service

[Install]
WantedBy=timers.target
EOF

echo "Wrote systemd unit files to $SYSTEMD_DIR"

# ── Enable and (re)start ─────────────────────────────────────────
systemctl --user daemon-reload
systemctl --user enable worktime-sync.timer
systemctl --user restart worktime-sync.timer
echo "Timer enabled and (re)started."

# ── Initial sync ─────────────────────────────────────────────────
echo ""
echo "Running initial sync..."
WORKTIME_SERVER_URL="$SERVER_URL" WORKTIME_COMPUTER_NAME="$COMPUTER_NAME" \
  python3 "$SYNC_PY"

echo ""
echo "Done."
echo "Next sync in ~1 min, then every 5 min."
echo "Logs: journalctl --user -u worktime-sync"
```

- [ ] **Step 2: Make it executable**

```bash
chmod +x ~/projects/personal/worktime-tracker/agents/ubuntu/install.sh
```

- [ ] **Step 3: Verify the script is valid bash (no syntax errors)**

```bash
bash -n ~/projects/personal/worktime-tracker/agents/ubuntu/install.sh
echo "exit code: $?"
```

Expected: no output, `exit code: 0`.

- [ ] **Step 4: Commit**

```bash
cd ~/projects/personal/worktime-tracker
git add agents/ubuntu/install.sh
git commit -m "feat: ubuntu agent install.sh — idempotent systemd setup"
```

---

## Task 4: End-to-End Verification

No automated tests for this task — verify manually against the running dev server.

**Prerequisite:** The dev server must be running:
```bash
cd ~/projects/personal/worktime-tracker/server
DATABASE_URL=sqlite:///./worktime_dev.db mise exec -- uvicorn main:app --reload --port 8000
```

- [ ] **Step 1: Run a manual sync against the dev server**

```bash
cd ~/projects/personal/worktime-tracker
WORKTIME_SERVER_URL=http://localhost:8000 \
WORKTIME_COMPUTER_NAME=test-ubuntu \
  mise exec -- python3 agents/ubuntu/sync.py
```

Expected output (numbers will vary):
```
Synced 42 events (42 inserted, 0 skipped)
```

- [ ] **Step 2: Confirm events appear in the server**

```bash
curl -s http://localhost:8000/api/sessions/computers
```

Expected: `["test-ubuntu"]` (plus any other computers from earlier seed data).

```bash
curl -s http://localhost:8000/api/summary/today | python3 -m json.tool | grep -E "hours_worked|status"
```

Expected: `hours_worked` reflects today's sessions, `status.computer` is `"test-ubuntu"` if a session is open.

- [ ] **Step 3: Re-run sync and confirm idempotency**

```bash
WORKTIME_SERVER_URL=http://localhost:8000 \
WORKTIME_COMPUTER_NAME=test-ubuntu \
  mise exec -- python3 agents/ubuntu/sync.py
```

Expected output:
```
Synced 42 events (0 inserted, 42 skipped)
```

All events are skipped because the server already has them (upsert on conflict).

- [ ] **Step 4: Run install.sh interactively**

```bash
cd ~/projects/personal/worktime-tracker
bash agents/ubuntu/install.sh
```

When prompted:
- Server URL: `http://localhost:8000` (or your actual server IP)
- Computer name: press Enter to accept the hostname default

Expected:
- Config file written
- Systemd units written
- Timer started without error
- Initial sync runs and prints the summary line
- Final message: "Next sync in ~1 min, then every 5 min."

- [ ] **Step 5: Verify the timer is running**

```bash
systemctl --user status worktime-sync.timer
```

Expected: `Active: active (waiting)` with a "Triggers:" line showing `worktime-sync.service`.

- [ ] **Step 6: Check the service can run via systemd**

```bash
systemctl --user start worktime-sync.service
journalctl --user -u worktime-sync -n 20
```

Expected: log line like `Synced N events (0 inserted, N skipped)` — all skipped since we just synced.

- [ ] **Step 7: Re-run install.sh to verify idempotency**

```bash
bash ~/projects/personal/worktime-tracker/agents/ubuntu/install.sh
```

When prompted, press Enter to accept all existing values unchanged.

Expected: same output as first run, timer restarts cleanly, sync re-runs (all skipped).

- [ ] **Step 8: Final commit**

```bash
cd ~/projects/personal/worktime-tracker
git add -A
git commit -m "chore: verified ubuntu agent end-to-end — agent plan complete"
```

---

## What's Next

This plan is complete when all 4 tasks are done and the timer is running on your Ubuntu machine.

Next plans:
1. **Windows agent plan** — `agents/windows/sync.ps1` + Task Scheduler installer
2. **Import existing Google Sheet data** — bulk import historical manual entries
