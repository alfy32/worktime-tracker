import pytest
from datetime import datetime, date, timedelta
from calculations import get_sessions, merge_intervals, calculate_work_hours, calculate_per_computer_hours
from calculations import weekdays_elapsed, calculate_hours_bank, remaining_weekdays_in_week, calculate_stop_time


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

    def test_orphaned_logout_ignored(self):
        events = [
            ev("ubuntu", "logout", datetime(2026, 5, 20, 7, 0)),
            ev("ubuntu", "login",  datetime(2026, 5, 20, 8, 0)),
            ev("ubuntu", "logout", datetime(2026, 5, 20, 12, 0)),
        ]
        assert get_sessions(events, NOW) == [
            (datetime(2026, 5, 20, 8, 0), datetime(2026, 5, 20, 12, 0))
        ]

    def test_double_login_uses_second(self):
        # If two logins arrive without a logout (e.g. missed crash logout),
        # the second login starts the session (first is lost — expected behavior).
        events = [
            ev("ubuntu", "login",  datetime(2026, 5, 20, 8, 0)),
            ev("ubuntu", "login",  datetime(2026, 5, 20, 9, 0)),
            ev("ubuntu", "logout", datetime(2026, 5, 20, 12, 0)),
        ]
        assert get_sessions(events, NOW) == [
            (datetime(2026, 5, 20, 9, 0), datetime(2026, 5, 20, 12, 0))
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
        assert merge_intervals(ivs) == [
            (datetime(2026, 5, 20, 8, 0),  datetime(2026, 5, 20, 12, 0)),
            (datetime(2026, 5, 20, 13, 0), datetime(2026, 5, 20, 17, 0)),
        ]


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


class TestWeekdaysElapsed:
    def test_full_work_week(self):
        # Mon May 18 to Mon May 25 = 5 weekdays
        assert weekdays_elapsed(date(2026, 5, 18), date(2026, 5, 25)) == 5

    def test_includes_start_excludes_end(self):
        assert weekdays_elapsed(date(2026, 5, 20), date(2026, 5, 21)) == 1

    def test_weekend_not_counted(self):
        # Sat to Mon = 0 (Sat and Sun are weekend)
        assert weekdays_elapsed(date(2026, 5, 23), date(2026, 5, 25)) == 0

    def test_same_date_returns_zero(self):
        assert weekdays_elapsed(date(2026, 5, 20), date(2026, 5, 20)) == 0


class TestHoursBank:
    def test_on_track(self):
        # 1 weekday elapsed, worked exactly 8h → bank = 0
        tracking_start = date(2026, 5, 20)
        now = datetime(2026, 5, 20, 17, 0)
        events = [
            ev("ubuntu", "login",  datetime(2026, 5, 20, 9, 0)),
            ev("ubuntu", "logout", datetime(2026, 5, 20, 17, 0)),
        ]
        assert calculate_hours_bank(events, [], tracking_start, 8.0, now) == pytest.approx(0.0)

    def test_ahead(self):
        tracking_start = date(2026, 5, 20)
        now = datetime(2026, 5, 20, 18, 0)
        events = [
            ev("ubuntu", "login",  datetime(2026, 5, 20, 9, 0)),
            ev("ubuntu", "logout", datetime(2026, 5, 20, 18, 0)),
        ]
        # Worked 9h, expected 8h → +1h bank
        assert calculate_hours_bank(events, [], tracking_start, 8.0, now) == pytest.approx(1.0)

    def test_behind(self):
        tracking_start = date(2026, 5, 20)
        now = datetime(2026, 5, 20, 16, 0)
        events = [
            ev("ubuntu", "login",  datetime(2026, 5, 20, 9, 0)),
            ev("ubuntu", "logout", datetime(2026, 5, 20, 16, 0)),
        ]
        # Worked 7h, expected 8h → -1h bank
        assert calculate_hours_bank(events, [], tracking_start, 8.0, now) == pytest.approx(-1.0)

    def test_manual_entry_counts(self):
        tracking_start = date(2026, 1, 1)
        now = datetime(2026, 1, 1, 12, 0)
        m = manual(date(2026, 1, 1), 8.0)
        # 1 weekday elapsed (Jan 1 is a Thursday), worked 8h manual → bank = 0
        assert calculate_hours_bank([], [m], tracking_start, 8.0, now) == pytest.approx(0.0)


class TestRemainingWeekdays:
    def test_monday(self):
        assert remaining_weekdays_in_week(date(2026, 5, 18)) == 5

    def test_wednesday(self):
        assert remaining_weekdays_in_week(date(2026, 5, 20)) == 3

    def test_friday(self):
        assert remaining_weekdays_in_week(date(2026, 5, 22)) == 1


class TestStopTime:
    def test_done_for_day(self):
        # Worked exactly 8h today, bank=0, Mon: all 5 days remain at 8h/day
        now = datetime(2026, 5, 18, 17, 0)  # Monday 5pm
        events = [
            ev("ubuntu", "login",  datetime(2026, 5, 18, 9, 0)),
            ev("ubuntu", "logout", datetime(2026, 5, 18, 17, 0)),
        ]
        result = calculate_stop_time(
            week_events=events, week_manual=[],
            today_events=events, today_manual=[],
            bank_at_week_start=0.0, weekly_target=40.0, now=now,
        )
        assert result is None

    def test_still_working(self):
        # Monday 12pm, worked 3h so far, need 8h today → stop at 5pm
        now = datetime(2026, 5, 18, 12, 0)
        events = [ev("ubuntu", "login", datetime(2026, 5, 18, 9, 0))]
        result = calculate_stop_time(
            week_events=events, week_manual=[],
            today_events=events, today_manual=[],
            bank_at_week_start=0.0, weekly_target=40.0, now=now,
        )
        assert result == pytest.approx(
            datetime(2026, 5, 18, 17, 0).timestamp(), abs=60
        )

    def test_banked_time_reduces_daily_target(self):
        # +8h banked → adjusted target = 32h → need 32/5 = 6.4h/day on Monday
        # Logged in at 9am, now = 15:24 (worked 6.4h) → should be done
        now = datetime(2026, 5, 18, 15, 24)
        events = [ev("ubuntu", "login", datetime(2026, 5, 18, 9, 0))]
        result = calculate_stop_time(
            week_events=events, week_manual=[],
            today_events=events, today_manual=[],
            bank_at_week_start=8.0, weekly_target=40.0, now=now,
        )
        assert result is None

    def test_behind_increases_daily_target(self):
        # -8h bank → adjusted target = 48h → need 48/5 = 9.6h/day on Monday
        # Worked 8h today → not done yet
        now = datetime(2026, 5, 18, 17, 0)
        events = [
            ev("ubuntu", "login",  datetime(2026, 5, 18, 9, 0)),
            ev("ubuntu", "logout", datetime(2026, 5, 18, 17, 0)),
        ]
        result = calculate_stop_time(
            week_events=events, week_manual=[],
            today_events=events, today_manual=[],
            bank_at_week_start=-8.0, weekly_target=40.0, now=now,
        )
        assert result is not None
        assert result > now.timestamp()
