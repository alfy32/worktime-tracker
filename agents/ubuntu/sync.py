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
    # First pass: identify all graphical sessions
    graphical_sessions = set()
    parsed_entries = []

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

        m = _NEW_SESSION.match(msg)
        if m:
            graphical_sessions.add(m.group(1))

        parsed_entries.append((ts_us, msg))

    # Second pass: generate events based on identified sessions
    events = []
    for ts_us, msg in parsed_entries:
        dt = datetime.fromtimestamp(int(ts_us) / 1_000_000)
        iso = dt.strftime('%Y-%m-%dT%H:%M:%S')

        m = _NEW_SESSION.match(msg)
        if m:
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
    """Return (server_url, computer_name) from env vars or config file."""
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
