from datetime import datetime, date, timedelta


def get_sessions(events: list, now: datetime) -> list[tuple[datetime, datetime]]:
    """
    Pair login/logout events for a single computer into (start, end) tuples.
    Non-work logins are excluded. An open login on today's date uses `now` as
    the end; open logins on earlier dates are excluded (0 hours contributed).
    Input need not be pre-sorted.
    """
    sessions = []
    pending_login: datetime | None = None
    pending_is_work: bool = True

    for event in sorted(events, key=lambda e: e.timestamp):
        if event.action == "login":
            pending_login = event.timestamp
            pending_is_work = event.is_work
        elif event.action == "logout" and pending_login is not None:
            if pending_is_work:
                sessions.append((pending_login, event.timestamp))
            pending_login = None

    if pending_login is not None and pending_is_work:
        if pending_login.date() >= now.date():
            sessions.append((pending_login, now))

    return sessions


def has_unclosed_login(events: list) -> bool:
    """Return True if any computer in events has a login with no matching logout."""
    for computer in {e.computer for e in events}:
        comp_events = sorted(
            [e for e in events if e.computer == computer],
            key=lambda e: e.timestamp,
        )
        pending = False
        for ev in comp_events:
            if ev.action == "login" and ev.is_work:
                pending = True
            elif ev.action == "logout" and pending:
                pending = False
        if pending:
            return True
    return False


def merge_intervals(
    intervals: list[tuple[datetime, datetime]],
) -> list[tuple[datetime, datetime]]:
    """Merge overlapping or adjacent datetime intervals into a minimal list."""
    if not intervals:
        return []
    sorted_ivs = sorted(intervals, key=lambda x: x[0])
    result: list[list] = [list(sorted_ivs[0])]
    for start, end in sorted_ivs[1:]:
        if start <= result[-1][1]:
            result[-1][1] = max(result[-1][1], end)
        else:
            result.append([start, end])
    return [(s, e) for s, e in result]


def calculate_work_hours(
    events: list, manual_entries: list, now: datetime
) -> float:
    """
    Total merged work hours from events (all computers) plus manual entries.
    Overlapping sessions across computers are merged — no double counting.
    """
    all_sessions: list[tuple[datetime, datetime]] = []
    for computer in {e.computer for e in events}:
        computer_events = [e for e in events if e.computer == computer]
        all_sessions.extend(get_sessions(computer_events, now))

    merged = merge_intervals(all_sessions)
    total = sum((end - start).total_seconds() / 3600 for start, end in merged)
    total += sum(m.hours for m in manual_entries)
    return total


def calculate_per_computer_hours(events: list, now: datetime) -> dict[str, float]:
    """Hours per computer without merging (overlapping time counted on each)."""
    result: dict[str, float] = {}
    for computer in {e.computer for e in events}:
        computer_events = [e for e in events if e.computer == computer]
        sessions = get_sessions(computer_events, now)
        result[computer] = sum(
            (end - start).total_seconds() / 3600 for start, end in sessions
        )
    return result


def weekdays_elapsed(start: date, end: date) -> int:
    """Count Mon–Fri days from start up to but not including end."""
    count = 0
    current = start
    while current < end:
        if current.weekday() < 5:
            count += 1
        current += timedelta(days=1)
    return count


def calculate_hours_bank(
    all_events: list,
    all_manual: list,
    tracking_start: date,
    daily_target: float,
    now: datetime,
) -> float:
    """
    Running bank = total hours worked − weekdays elapsed × daily_target.
    Positive = ahead of schedule, negative = behind.
    Today counts as an elapsed weekday (end is exclusive, so pass tomorrow).
    """
    end = now.date() + timedelta(days=1)
    expected = weekdays_elapsed(tracking_start, end) * daily_target
    worked = calculate_work_hours(all_events, all_manual, now)
    return worked - expected


def remaining_weekdays_in_week(today: date) -> int:
    """Count weekdays from today through Friday, inclusive."""
    return sum(1 for d in range(today.weekday(), 5))


def calculate_stop_time(
    week_events: list,
    week_manual: list,
    today_events: list,
    today_manual: list,
    bank_at_week_start: float,
    weekly_target: float,
    now: datetime,
) -> datetime | None:
    """
    Return the datetime today when the user can stop to stay on track for the week.
    Returns None if today's required hours are already met.

    adjusted_target = weekly_target - bank_at_week_start, clamped to [0, weekly_target * 1.5].
    hours_needed_today = (adjusted_target - hours_worked_before_today) / remaining_weekdays.
    """
    today = now.date()

    if today.weekday() >= 5:
        return None

    adjusted_target = weekly_target - bank_at_week_start
    adjusted_target = max(0.0, min(adjusted_target, weekly_target * 1.5))

    pre_today_events = [e for e in week_events if e.timestamp.date() < today]
    pre_today_manual = [m for m in week_manual if m.date < today]
    hours_before_today = calculate_work_hours(pre_today_events, pre_today_manual, now)

    remaining_days = remaining_weekdays_in_week(today) or 1
    hours_needed_today = (adjusted_target - hours_before_today) / remaining_days
    hours_today = calculate_work_hours(today_events, today_manual, now)

    remaining = hours_needed_today - hours_today
    if remaining <= 0:
        return None

    return now + timedelta(hours=remaining)
