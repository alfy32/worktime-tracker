from datetime import datetime, date, timedelta
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
from models import Event, ManualEntry, Settings
from schemas import (
    TodaySummary, WeekSummary, DailySummary, WeeklySummary,
    SessionOut, ComputerStatus, DayBreakdown, DayStats, WeekStats,
)
from calculations import (
    calculate_work_hours, calculate_per_computer_hours,
    calculate_hours_bank, calculate_stop_time,
    get_sessions, merge_intervals, remaining_weekdays_in_week, weekdays_elapsed,
)
from session_utils import build_sessions

router = APIRouter()


def _get_cfg(db: Session) -> dict:
    rows = {s.key: s.value for s in db.query(Settings).all()}
    if "tracking_start_date" in rows:
        tracking_start = date.fromisoformat(rows["tracking_start_date"])
    else:
        first = db.query(Event).order_by(Event.timestamp).first()
        tracking_start = first.timestamp.date() if first else date.today()
    return {
        "weekly_target": float(rows.get("weekly_target_hours", "40")),
        "daily_target":  float(rows.get("daily_target_hours",  "8")),
        "tracking_start": tracking_start,
    }


def _day_events(db: Session, d: date) -> list:
    start = datetime.combine(d, datetime.min.time())
    end   = datetime.combine(d + timedelta(days=1), datetime.min.time())
    return db.query(Event).filter(Event.timestamp >= start, Event.timestamp < end).all()


def _day_manual(db: Session, d: date) -> list:
    return db.query(ManualEntry).filter(ManualEntry.date == d).all()


@router.get("/api/summary/today", response_model=TodaySummary)
def summary_today(db: Session = Depends(get_db)):
    now   = datetime.now()
    today = now.date()
    cfg   = _get_cfg(db)

    today_events = _day_events(db, today)
    today_manual = _day_manual(db, today)

    week_start = today - timedelta(days=today.weekday())
    week_start_dt = datetime.combine(week_start, datetime.min.time())
    today_end_dt  = datetime.combine(today + timedelta(days=1), datetime.min.time())

    week_events = db.query(Event).filter(
        Event.timestamp >= week_start_dt,
        Event.timestamp < today_end_dt,
    ).all()
    week_manual = db.query(ManualEntry).filter(
        ManualEntry.date >= week_start,
        ManualEntry.date <= today,
    ).all()

    all_events = db.query(Event).all()
    all_manual = db.query(ManualEntry).all()

    # Bank at the start of this week (exclude this week's hours)
    pre_week_events = [e for e in all_events if e.timestamp.date() < week_start]
    pre_week_manual = [m for m in all_manual if m.date < week_start]
    bank_at_week_start = (
        calculate_work_hours(pre_week_events, pre_week_manual, week_start_dt)
        - weekdays_elapsed(cfg["tracking_start"], week_start) * cfg["daily_target"]
    )

    hours_worked   = calculate_work_hours(today_events, today_manual, now)
    per_computer   = calculate_per_computer_hours(today_events, now)
    bank_now       = calculate_hours_bank(all_events, all_manual, cfg["tracking_start"], cfg["daily_target"], now)
    stop_time      = calculate_stop_time(
        week_events=week_events, week_manual=week_manual,
        today_events=today_events, today_manual=today_manual,
        bank_at_week_start=bank_at_week_start,
        weekly_target=cfg["weekly_target"], now=now,
    )
    hours_remaining = round((stop_time - now).total_seconds() / 3600, 2) if stop_time else 0.0

    # Report logged_in=True if any computer's most recent event is a login
    computers = {e.computer for e in all_events}
    status_computer: str | None = None
    status_since: datetime | None = None
    status_logged_in = False
    for comp in computers:
        last = max((e for e in all_events if e.computer == comp), key=lambda e: e.timestamp)
        if last.action == "login":
            if not status_logged_in or last.timestamp > (status_since or last.timestamp):
                status_computer = comp
                status_since = last.timestamp
                status_logged_in = True
        elif not status_logged_in:
            if status_since is None or last.timestamp > status_since:
                status_computer = comp
                status_since = last.timestamp
    status = ComputerStatus(
        computer=status_computer,
        logged_in=status_logged_in,
        since=status_since,
    )

    return TodaySummary(
        hours_worked=round(hours_worked, 2),
        hours_remaining=hours_remaining,
        stop_time=stop_time,
        bank_hours=round(bank_now, 2),
        per_computer=per_computer,
        sessions=build_sessions(today_events, now),
        status=status,
    )


@router.get("/api/summary/week", response_model=WeekSummary)
def summary_week(db: Session = Depends(get_db)):
    now        = datetime.now()
    today      = now.date()
    cfg        = _get_cfg(db)
    week_start = today - timedelta(days=today.weekday())

    all_events = db.query(Event).all()
    all_manual = db.query(ManualEntry).all()
    week_start_dt = datetime.combine(week_start, datetime.min.time())

    pre_week_events = [e for e in all_events if e.timestamp.date() < week_start]
    pre_week_manual = [m for m in all_manual if m.date < week_start]
    bank_at_week_start = (
        calculate_work_hours(pre_week_events, pre_week_manual, week_start_dt)
        - weekdays_elapsed(cfg["tracking_start"], week_start) * cfg["daily_target"]
    )

    adjusted_target = max(0.0, min(cfg["weekly_target"] - bank_at_week_start, cfg["weekly_target"] * 1.5))

    breakdown = []
    total_hours = 0.0
    for i in range(7):
        d = week_start + timedelta(days=i)
        if d > today:
            break
        d_events = _day_events(db, d)
        d_manual = _day_manual(db, d)
        end_of_day = datetime.combine(d + timedelta(days=1), datetime.min.time())
        cutoff = now if d == today else end_of_day
        hours = calculate_work_hours(d_events, d_manual, cutoff)
        total_hours += hours
        breakdown.append(DayBreakdown(date=d, hours=round(hours, 2), is_today=(d == today)))

    remaining_weekdays = remaining_weekdays_in_week(today)
    hours_remaining = max(0.0, round(adjusted_target - total_hours, 2))

    return WeekSummary(
        week_start=week_start,
        total_hours=round(total_hours, 2),
        weekly_target=cfg["weekly_target"],
        adjusted_target=round(adjusted_target, 2),
        hours_remaining=hours_remaining,
        remaining_weekdays=remaining_weekdays,
        daily_breakdown=breakdown,
    )


def _longest_break(events: list, now: datetime) -> float:
    """Find the longest gap between merged sessions for a single day's events."""
    all_sessions = []
    for computer in {e.computer for e in events}:
        comp_events = [e for e in events if e.computer == computer]
        all_sessions.extend(get_sessions(comp_events, now))
    merged = merge_intervals(all_sessions)
    if len(merged) < 2:
        return 0.0
    max_gap = 0.0
    for i in range(1, len(merged)):
        gap = (merged[i][0] - merged[i - 1][1]).total_seconds() / 3600
        max_gap = max(max_gap, gap)
    return round(max_gap, 2)


@router.get("/api/summary/daily", response_model=DailySummary)
def summary_daily(days: int = 60, db: Session = Depends(get_db)):
    now   = datetime.now()
    today = now.date()
    result = []
    for i in range(days - 1, -1, -1):
        d = today - timedelta(days=i)
        d_events = _day_events(db, d)
        d_manual = _day_manual(db, d)
        end_of_day = datetime.combine(d + timedelta(days=1), datetime.min.time())
        cutoff = now if d == today else end_of_day
        hours = calculate_work_hours(d_events, d_manual, cutoff)
        sessions_count = sum(
            len(get_sessions([e for e in d_events if e.computer == c], cutoff))
            for c in {e.computer for e in d_events}
        )
        result.append(DayStats(
            date=d,
            hours=round(hours, 2),
            session_count=sessions_count,
            longest_break_hours=_longest_break(d_events, cutoff),
        ))
    return DailySummary(days=result)


@router.get("/api/summary/weekly", response_model=WeeklySummary)
def summary_weekly(weeks: int = 26, db: Session = Depends(get_db)):
    now        = datetime.now()
    today      = now.date()
    week_start = today - timedelta(days=today.weekday())
    result     = []
    for i in range(weeks - 1, -1, -1):
        ws = week_start - timedelta(weeks=i)
        we = ws + timedelta(days=6)
        w_events = db.query(Event).filter(
            Event.timestamp >= datetime.combine(ws, datetime.min.time()),
            Event.timestamp <  datetime.combine(we + timedelta(days=1), datetime.min.time()),
        ).all()
        w_manual = db.query(ManualEntry).filter(
            ManualEntry.date >= ws,
            ManualEntry.date <= min(we, today),
        ).all()
        end_of_week = datetime.combine(we + timedelta(days=1), datetime.min.time())
        cap = now if we >= today else end_of_week
        total = calculate_work_hours(w_events, w_manual, cap)
        worked_days = weekdays_elapsed(ws, min(we + timedelta(days=1), today + timedelta(days=1)))
        avg = round(total / worked_days, 2) if worked_days else 0.0
        result.append(WeekStats(
            week_start=ws,
            total_hours=round(total, 2),
            avg_hours_per_day=avg,
            delta_from_40=round(total - 40.0, 2),
        ))
    return WeeklySummary(weeks=result)
