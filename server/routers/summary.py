from datetime import datetime, date, timedelta
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
from models import Event, ManualEntry, Settings
from schemas import (
    TodaySummary, WeekSummary,
    SessionOut, ComputerStatus, DayBreakdown,
)
from calculations import (
    calculate_work_hours, calculate_per_computer_hours,
    calculate_hours_bank, calculate_stop_time,
    get_sessions, remaining_weekdays_in_week, weekdays_elapsed,
)
from session_utils import build_sessions

router = APIRouter()


def _get_cfg(db: Session) -> dict:
    rows = {s.key: s.value for s in db.query(Settings).all()}
    return {
        "weekly_target": float(rows.get("weekly_target_hours", "40")),
        "daily_target":  float(rows.get("daily_target_hours",  "8")),
        "tracking_start": date.fromisoformat(rows.get("tracking_start_date", "2026-01-01")),
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

    latest = max(all_events, key=lambda e: e.timestamp, default=None)
    status = ComputerStatus(
        computer=latest.computer if latest else None,
        logged_in=(latest.action == "login") if latest else False,
        since=latest.timestamp if latest else None,
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
        hours = calculate_work_hours(d_events, d_manual, now)
        total_hours += hours
        breakdown.append(DayBreakdown(date=d, hours=round(hours, 2), is_today=(d == today)))

    remaining_weekdays = remaining_weekdays_in_week(today)
    hours_remaining = max(0.0, round(adjusted_target - total_hours, 2))

    return WeekSummary(
        week_start=week_start,
        total_hours=round(total_hours, 2),
        adjusted_target=round(adjusted_target, 2),
        hours_remaining=hours_remaining,
        remaining_weekdays=remaining_weekdays,
        daily_breakdown=breakdown,
    )
