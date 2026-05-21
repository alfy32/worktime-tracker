import pytest
from datetime import datetime, date, timedelta
from calculations import get_sessions, merge_intervals, calculate_work_hours, calculate_per_computer_hours


def ev(computer, action, ts, is_work=True):
    class E:
        pass
    e = E()
    e.computer = computer
    e.action = action
    e.timestamp = ts
    e.is_work = is_work
    return e


def manual(d, hours):
    class M:
        pass
    m = M()
    m.date = d
    m.hours = hours
    return m


NOW = datetime(2026, 5, 20, 14, 0)  # Wednesday 2pm


class TestGetSessions:
    def test_simple_pair(self):
        events = [
            ev("ubuntu", "login",  datetime(2026, 5, 20, 8, 0)),
            ev("ubuntu", "logout", datetime(2026, 5, 20, 12, 0)),
        ]
        assert get_sessions(events, NOW) == [
            (datetime(2026, 5, 20, 8, 0), datetime(2026, 5, 20, 12, 0))
        ]

    def test_open_session_uses_now(self):
        events = [ev("ubuntu", "login", datetime(2026, 5, 20, 8, 0))]
        assert get_sessions(events, NOW) == [(datetime(2026, 5, 20, 8, 0), NOW)]

    def test_non_work_session_excluded(self):
        events = [
            ev("ubuntu", "login",  datetime(2026, 5, 20, 8, 0), is_work=False),
            ev("ubuntu", "logout", datetime(2026, 5, 20, 12, 0)),
        ]
        assert get_sessions(events, NOW) == []

    def test_multiple_sessions(self):
        events = [
            ev("ubuntu", "login",  datetime(2026, 5, 20, 8, 0)),
            ev("ubuntu", "logout", datetime(2026, 5, 20, 12, 0)),
            ev("ubuntu", "login",  datetime(2026, 5, 20, 13, 0)),
            ev("ubuntu", "logout", datetime(2026, 5, 20, 17, 0)),
        ]
        sessions = get_sessions(events, NOW)
        assert len(sessions) == 2
        assert sessions[0] == (datetime(2026, 5, 20, 8, 0), datetime(2026, 5, 20, 12, 0))
        assert sessions[1] == (datetime(2026, 5, 20, 13, 0), datetime(2026, 5, 20, 17, 0))

    def test_unsorted_input_handled(self):
        events = [
            ev("ubuntu", "logout", datetime(2026, 5, 20, 12, 0)),
            ev("ubuntu", "login",  datetime(2026, 5, 20, 8, 0)),
        ]
        assert get_sessions(events, NOW) == [
            (datetime(2026, 5, 20, 8, 0), datetime(2026, 5, 20, 12, 0))
        ]


class TestMergeIntervals:
    def test_empty(self):
        assert merge_intervals([]) == []

    def test_no_overlap(self):
        ivs = [
            (datetime(2026, 5, 20, 8, 0),  datetime(2026, 5, 20, 12, 0)),
            (datetime(2026, 5, 20, 13, 0), datetime(2026, 5, 20, 17, 0)),
        ]
        assert merge_intervals(ivs) == ivs

    def test_overlap_merged(self):
        ivs = [
            (datetime(2026, 5, 20, 8, 0),  datetime(2026, 5, 20, 12, 0)),
            (datetime(2026, 5, 20, 10, 0), datetime(2026, 5, 20, 14, 0)),
        ]
        assert merge_intervals(ivs) == [
            (datetime(2026, 5, 20, 8, 0), datetime(2026, 5, 20, 14, 0))
        ]

    def test_contained_interval(self):
        ivs = [
            (datetime(2026, 5, 20, 8, 0),  datetime(2026, 5, 20, 17, 0)),
            (datetime(2026, 5, 20, 10, 0), datetime(2026, 5, 20, 12, 0)),
        ]
        assert merge_intervals(ivs) == [
            (datetime(2026, 5, 20, 8, 0), datetime(2026, 5, 20, 17, 0))
        ]

    def test_unsorted_input_handled(self):
        ivs = [
            (datetime(2026, 5, 20, 13, 0), datetime(2026, 5, 20, 17, 0)),
            (datetime(2026, 5, 20, 8, 0),  datetime(2026, 5, 20, 12, 0)),
        ]
        result = merge_intervals(ivs)
        assert result[0][0] == datetime(2026, 5, 20, 8, 0)


class TestCalculateWorkHours:
    def test_two_computers_overlap_merged(self):
        # Ubuntu 8–12, Windows 10–14 → merged 8–14 = 6h
        events = [
            ev("ubuntu",  "login",  datetime(2026, 5, 20, 8, 0)),
            ev("ubuntu",  "logout", datetime(2026, 5, 20, 12, 0)),
            ev("windows", "login",  datetime(2026, 5, 20, 10, 0)),
            ev("windows", "logout", datetime(2026, 5, 20, 14, 0)),
        ]
        assert calculate_work_hours(events, [], NOW) == pytest.approx(6.0)

    def test_manual_entries_added(self):
        m = manual(date(2026, 1, 1), 8.0)
        assert calculate_work_hours([], [m], NOW) == pytest.approx(8.0)

    def test_non_work_session_excluded(self):
        events = [
            ev("ubuntu", "login",  datetime(2026, 5, 20, 8, 0)),
            ev("ubuntu", "logout", datetime(2026, 5, 20, 12, 0)),
            ev("ubuntu", "login",  datetime(2026, 5, 20, 13, 0), is_work=False),
            ev("ubuntu", "logout", datetime(2026, 5, 20, 17, 0)),
        ]
        assert calculate_work_hours(events, [], NOW) == pytest.approx(4.0)

    def test_no_events_returns_zero(self):
        assert calculate_work_hours([], [], NOW) == pytest.approx(0.0)


class TestCalculatePerComputerHours:
    def test_both_computers_tracked_separately(self):
        events = [
            ev("ubuntu",  "login",  datetime(2026, 5, 20, 8, 0)),
            ev("ubuntu",  "logout", datetime(2026, 5, 20, 12, 0)),
            ev("windows", "login",  datetime(2026, 5, 20, 10, 0)),
            ev("windows", "logout", datetime(2026, 5, 20, 14, 0)),
        ]
        result = calculate_per_computer_hours(events, NOW)
        assert result["ubuntu"]  == pytest.approx(4.0)
        assert result["windows"] == pytest.approx(4.0)

    def test_overlap_not_merged_per_computer(self):
        # Both computers on from 8–12: ubuntu=4h, windows=4h (not merged to 4h total)
        events = [
            ev("ubuntu",  "login",  datetime(2026, 5, 20, 8, 0)),
            ev("ubuntu",  "logout", datetime(2026, 5, 20, 12, 0)),
            ev("windows", "login",  datetime(2026, 5, 20, 8, 0)),
            ev("windows", "logout", datetime(2026, 5, 20, 12, 0)),
        ]
        result = calculate_per_computer_hours(events, NOW)
        assert result["ubuntu"]  == pytest.approx(4.0)
        assert result["windows"] == pytest.approx(4.0)
