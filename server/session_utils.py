from datetime import datetime
from schemas import SessionOut


def build_sessions(events: list, now: datetime) -> list[SessionOut]:
    """
    Convert raw Event rows into paired SessionOut objects.
    Open sessions (no matching logout) use `now` as the end.
    Returns sessions sorted ascending by login_at.
    """
    result = []
    for computer in sorted({e.computer for e in events}):
        comp_events = sorted(
            [e for e in events if e.computer == computer],
            key=lambda e: e.timestamp,
        )
        pending = None
        pending_ev = None
        for ev in comp_events:
            if ev.action == "login":
                pending = ev.timestamp
                pending_ev = ev
            elif ev.action == "logout" and pending is not None:
                dur = (ev.timestamp - pending).total_seconds() / 3600
                result.append(SessionOut(
                    id=pending_ev.id, computer=computer,
                    login_at=pending, logout_at=ev.timestamp,
                    duration_hours=round(dur, 2),
                    is_work=pending_ev.is_work, is_active=False,
                    note=pending_ev.note,
                ))
                pending = None
        if pending is not None and pending_ev is not None:
            dur = (now - pending).total_seconds() / 3600
            result.append(SessionOut(
                id=pending_ev.id, computer=computer,
                login_at=pending, logout_at=None,
                duration_hours=round(dur, 2),
                is_work=pending_ev.is_work, is_active=True,
                note=pending_ev.note,
            ))
    return sorted(result, key=lambda s: s.login_at)
