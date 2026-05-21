from datetime import datetime, date
from pydantic import BaseModel


class SyncEvent(BaseModel):
    timestamp: datetime
    action: str


class SyncRequest(BaseModel):
    computer: str
    events: list[SyncEvent]


class SyncResponse(BaseModel):
    inserted: int
    skipped: int


class SessionOut(BaseModel):
    id: int
    computer: str
    login_at: datetime
    logout_at: datetime | None
    duration_hours: float
    is_work: bool
    is_active: bool
    note: str | None = None

    model_config = {"from_attributes": True}


class ComputerStatus(BaseModel):
    computer: str | None
    logged_in: bool
    since: datetime | None


class TodaySummary(BaseModel):
    hours_worked: float
    hours_remaining: float
    stop_time: datetime | None
    bank_hours: float
    per_computer: dict[str, float]
    sessions: list[SessionOut]
    status: ComputerStatus


class DayBreakdown(BaseModel):
    date: date
    hours: float
    is_today: bool


class WeekSummary(BaseModel):
    week_start: date
    total_hours: float
    adjusted_target: float
    hours_remaining: float
    remaining_weekdays: int
    daily_breakdown: list[DayBreakdown]


class DayStats(BaseModel):
    date: date
    hours: float
    session_count: int
    longest_break_hours: float


class DailySummary(BaseModel):
    days: list[DayStats]


class WeekStats(BaseModel):
    week_start: date
    total_hours: float
    avg_hours_per_day: float
    delta_from_40: float


class WeeklySummary(BaseModel):
    weeks: list[WeekStats]


class SessionsResponse(BaseModel):
    sessions: list[SessionOut]
    total: int
    page: int
    per_page: int


class PatchSession(BaseModel):
    is_work: bool
    note: str | None = None


class ManualEntryIn(BaseModel):
    date: date
    hours: float = 8.0
    note: str | None = None


class ManualEntryOut(BaseModel):
    id: int
    date: date
    hours: float
    note: str | None

    model_config = {"from_attributes": True}


class SettingsOut(BaseModel):
    weekly_target_hours: float
    daily_target_hours: float
    tracking_start_date: date


class SettingsIn(BaseModel):
    weekly_target_hours: float | None = None
    daily_target_hours: float | None = None
    tracking_start_date: date | None = None
