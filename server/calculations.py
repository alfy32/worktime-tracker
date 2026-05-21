from datetime import datetime, date, timedelta


def get_sessions(events: list, now: datetime) -> list[tuple[datetime, datetime]]:
    """
    Pair login/logout events for a single computer into (start, end) tuples.
    Non-work logins are excluded. An open login uses `now` as the end.
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
        sessions.append((pending_login, now))

    return sessions


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
