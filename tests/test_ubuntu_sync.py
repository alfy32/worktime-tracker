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
        events = parse_events(lines)
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
