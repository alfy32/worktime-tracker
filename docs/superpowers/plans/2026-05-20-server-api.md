# Work Time Tracker — Server & API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the FastAPI + SQLite backend in Docker that receives login events from sync agents, calculates work hours with overlap merging and a running hours bank, and exposes a REST API for the web UI.

**Architecture:** Single FastAPI app in Docker. SQLite via SQLAlchemy for persistence. All hour math (session pairing, overlap merging, bank, stop time) lives in a pure `calculations.py` that is unit-tested independently. Routers are thin — they query the DB and call calculations. The `static/` directory is a placeholder for the UI (separate plan).

**Tech Stack:** Python 3.12, FastAPI 0.115, SQLAlchemy 2.0, SQLite, Pydantic 2.10, pytest, httpx (TestClient), Docker Compose

---

## File Map

| File | Purpose |
|------|---------|
| `pyproject.toml` | pytest config |
| `docker-compose.yml` | Service definition + named volume |
| `server/Dockerfile` | Python 3.12-slim, installs deps, runs uvicorn |
| `server/requirements.txt` | All Python deps |
| `server/main.py` | FastAPI app, router registration, DB init on startup, static file mount |
| `server/database.py` | SQLAlchemy engine, session factory, `get_db` dependency |
| `server/models.py` | `Event`, `ManualEntry`, `Settings` ORM models |
| `server/schemas.py` | All Pydantic request/response models |
| `server/calculations.py` | Pure functions: session pairing, merge intervals, bank, stop time |
| `server/session_utils.py` | `build_sessions()` — shared by summary and sessions routers |
| `server/routers/__init__.py` | Empty |
| `server/routers/sync.py` | `POST /api/sync` |
| `server/routers/summary.py` | `GET /api/summary/today`, `/week`, `/daily`, `/weekly` |
| `server/routers/sessions.py` | `GET /api/sessions`, `PATCH /api/sessions/{id}` |
| `server/routers/manual.py` | `POST /api/manual`, `DELETE /api/manual/{id}`, `GET/PUT /api/settings` |
| `server/static/.gitkeep` | Placeholder for UI files |
| `tests/conftest.py` | In-memory DB fixture + TestClient fixture |
| `tests/test_calculations.py` | Unit tests for all calculation functions |
| `tests/test_sync.py` | API tests for sync endpoint |
| `tests/test_summary.py` | API tests for summary endpoints |
| `tests/test_sessions.py` | API tests for sessions endpoint |
| `tests/test_manual.py` | API tests for manual entries + settings |

---

## Task 1: Project Scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `docker-compose.yml`
- Create: `server/Dockerfile`
- Create: `server/requirements.txt`
- Create: `server/static/.gitkeep`
- Create: `server/routers/__init__.py`

- [ ] **Step 1: Create directory structure**

```bash
mkdir -p server/routers server/static tests
touch server/routers/__init__.py server/static/.gitkeep
```

- [ ] **Step 2: Create `pyproject.toml`**

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["server"]
```

- [ ] **Step 3: Create `server/requirements.txt`**

```
fastapi==0.115.0
uvicorn[standard]==0.32.0
sqlalchemy==2.0.36
pydantic==2.10.3
pytest==8.3.4
httpx==0.28.1
freezegun==1.5.1
```

- [ ] **Step 4: Create `server/Dockerfile`**

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 5: Create `docker-compose.yml`**

```yaml
services:
  server:
    build: ./server
    ports:
      - "8000:8000"
    volumes:
      - worktime_data:/app/data
    environment:
      - DATABASE_URL=sqlite:////app/data/worktime.db
    restart: unless-stopped

volumes:
  worktime_data:
```

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml docker-compose.yml server/Dockerfile server/requirements.txt server/routers/__init__.py server/static/.gitkeep
git commit -m "chore: project scaffolding for server"
```

---

## Task 2: Database Setup

**Files:**
- Create: `server/database.py`
- Create: `server/models.py`

- [ ] **Step 1: Create `server/database.py`**

```python
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./worktime.db")

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

- [ ] **Step 2: Create `server/models.py`**

```python
from datetime import datetime, date
from sqlalchemy import String, Integer, Boolean, Float, DateTime, Date, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from database import Base


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (UniqueConstraint("computer", "timestamp", "action", name="uq_event"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    computer: Mapped[str] = mapped_column(String, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    action: Mapped[str] = mapped_column(String, nullable=False)
    is_work: Mapped[bool] = mapped_column(Boolean, default=True)
    note: Mapped[str | None] = mapped_column(String, nullable=True)


class ManualEntry(Base):
    __tablename__ = "manual_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    hours: Mapped[float] = mapped_column(Float, default=8.0)
    note: Mapped[str | None] = mapped_column(String, nullable=True)


class Settings(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str] = mapped_column(String, nullable=False)
```

- [ ] **Step 3: Write a quick smoke test**

Create `tests/test_models.py`:

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'server'))

from database import Base
from models import Event, ManualEntry, Settings
from datetime import datetime, date


def test_tables_create():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    db.add(Event(computer="ubuntu", timestamp=datetime(2026, 5, 20, 9, 0), action="login"))
    db.add(ManualEntry(date=date(2026, 1, 1), hours=8.0, note="New Years Day"))
    db.add(Settings(key="weekly_target_hours", value="40"))
    db.commit()

    assert db.query(Event).count() == 1
    assert db.query(ManualEntry).count() == 1
    assert db.query(Settings).count() == 1
    db.close()


def test_event_unique_constraint():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    ts = datetime(2026, 5, 20, 9, 0)
    db.add(Event(computer="ubuntu", timestamp=ts, action="login"))
    db.commit()

    from sqlalchemy.exc import IntegrityError
    import pytest
    with pytest.raises(IntegrityError):
        db.add(Event(computer="ubuntu", timestamp=ts, action="login"))
        db.commit()
    db.close()
```

- [ ] **Step 4: Run tests**

```bash
cd ~/projects/personal/worktime-tracker
pytest tests/test_models.py -v
```

Expected: `2 passed`

- [ ] **Step 5: Commit**

```bash
git add server/database.py server/models.py tests/test_models.py
git commit -m "feat: database models for events, manual entries, and settings"
```

---

## Task 3: Pydantic Schemas

**Files:**
- Create: `server/schemas.py`

No tests — schemas are validated by FastAPI automatically.

- [ ] **Step 1: Create `server/schemas.py`**

```python
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
```

- [ ] **Step 2: Commit**

```bash
git add server/schemas.py
git commit -m "feat: pydantic schemas for all API request/response models"
```

---

## Task 4: Core Calculations — Session Pairing & Interval Merging

**Files:**
- Create: `server/calculations.py`
- Create: `tests/test_calculations.py`

- [ ] **Step 1: Write failing tests for `get_sessions` and `merge_intervals`**

Create `tests/test_calculations.py`:

```python
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
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/test_calculations.py -v
```

Expected: `ImportError` — `calculations` module doesn't exist yet.

- [ ] **Step 3: Create `server/calculations.py` with `get_sessions`, `merge_intervals`, `calculate_work_hours`, `calculate_per_computer_hours`**

```python
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
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_calculations.py::TestGetSessions tests/test_calculations.py::TestMergeIntervals tests/test_calculations.py::TestCalculateWorkHours tests/test_calculations.py::TestCalculatePerComputerHours -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add server/calculations.py tests/test_calculations.py
git commit -m "feat: session pairing, interval merging, and work hour calculations"
```

---

## Task 5: Core Calculations — Hours Bank & Stop Time

**Files:**
- Modify: `server/calculations.py`
- Modify: `tests/test_calculations.py`

- [ ] **Step 1: Add failing tests for `weekdays_elapsed`, `calculate_hours_bank`, `remaining_weekdays_in_week`, `calculate_stop_time`**

Append to `tests/test_calculations.py`:

```python
from calculations import weekdays_elapsed, calculate_hours_bank, remaining_weekdays_in_week, calculate_stop_time


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
        assert result > now
```

- [ ] **Step 2: Run to confirm failures**

```bash
pytest tests/test_calculations.py::TestWeekdaysElapsed tests/test_calculations.py::TestHoursBank tests/test_calculations.py::TestRemainingWeekdays tests/test_calculations.py::TestStopTime -v
```

Expected: `ImportError` — functions not yet defined.

- [ ] **Step 3: Add the four functions to `server/calculations.py`**

Append to `server/calculations.py`:

```python
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
    """
    expected = weekdays_elapsed(tracking_start, now.date()) * daily_target
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
```

- [ ] **Step 4: Run all calculation tests**

```bash
pytest tests/test_calculations.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add server/calculations.py tests/test_calculations.py
git commit -m "feat: hours bank, stop time, and weekday calculations"
```

---

## Task 6: Shared Test Fixtures

**Files:**
- Create: `tests/conftest.py`

- [ ] **Step 1: Create `tests/conftest.py`**

```python
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base, get_db
from main import app
from models import Settings


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    session.add_all([
        Settings(key="weekly_target_hours",  value="40"),
        Settings(key="daily_target_hours",   value="8"),
        Settings(key="tracking_start_date",  value="2026-01-01"),
    ])
    session.commit()
    yield session
    session.close()
    Base.metadata.drop_all(engine)


@pytest.fixture
def client(db):
    def override():
        yield db
    app.dependency_overrides[get_db] = override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
```

Note: `conftest.py` imports from `main`, which doesn't exist yet. Create a minimal `server/main.py` placeholder now so imports don't fail:

- [ ] **Step 2: Create `server/session_utils.py`**

Both `summary.py` and `sessions.py` need to convert raw events into `SessionOut` objects. Define it once here.

```python
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
```

- [ ] **Step 3: Create minimal `server/main.py`**

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from database import engine, Base, SessionLocal
from models import Settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    defaults = {
        "weekly_target_hours": "40",
        "daily_target_hours":  "8",
        "tracking_start_date": "2026-01-01",
    }
    for key, value in defaults.items():
        if not db.query(Settings).filter(Settings.key == key).first():
            db.add(Settings(key=key, value=value))
    db.commit()
    db.close()
    yield


app = FastAPI(title="Work Time Tracker", lifespan=lifespan)
app.mount("/", StaticFiles(directory="static", html=True), name="static")
```

- [ ] **Step 3: Verify conftest is importable**

```bash
pytest tests/test_models.py -v
```

Expected: 2 passed (same as before — confirms conftest doesn't break existing tests).

- [ ] **Step 4: Commit**

```bash
git add tests/conftest.py server/main.py
git commit -m "feat: shared test fixtures and minimal FastAPI app skeleton"
```

---

## Task 7: Sync Endpoint

**Files:**
- Create: `server/routers/sync.py`
- Create: `tests/test_sync.py`
- Modify: `server/main.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_sync.py`:

```python
from datetime import datetime


def test_sync_inserts_new_events(client):
    resp = client.post("/api/sync", json={
        "computer": "ubuntu",
        "events": [
            {"timestamp": "2026-05-20T08:00:00", "action": "login"},
            {"timestamp": "2026-05-20T12:00:00", "action": "logout"},
        ],
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["inserted"] == 2
    assert data["skipped"] == 0


def test_sync_skips_duplicates(client):
    payload = {
        "computer": "ubuntu",
        "events": [{"timestamp": "2026-05-20T08:00:00", "action": "login"}],
    }
    client.post("/api/sync", json=payload)
    resp = client.post("/api/sync", json=payload)
    assert resp.status_code == 200
    assert resp.json()["inserted"] == 0
    assert resp.json()["skipped"] == 1


def test_sync_partial_duplicates(client):
    client.post("/api/sync", json={
        "computer": "windows",
        "events": [{"timestamp": "2026-05-20T08:00:00", "action": "login"}],
    })
    resp = client.post("/api/sync", json={
        "computer": "windows",
        "events": [
            {"timestamp": "2026-05-20T08:00:00", "action": "login"},   # duplicate
            {"timestamp": "2026-05-20T12:00:00", "action": "logout"},  # new
        ],
    })
    assert resp.json()["inserted"] == 1
    assert resp.json()["skipped"] == 1


def test_sync_different_computers_dont_conflict(client):
    payload = {"events": [{"timestamp": "2026-05-20T08:00:00", "action": "login"}]}
    r1 = client.post("/api/sync", json={**payload, "computer": "ubuntu"})
    r2 = client.post("/api/sync", json={**payload, "computer": "windows"})
    assert r1.json()["inserted"] == 1
    assert r2.json()["inserted"] == 1
```

- [ ] **Step 2: Run to confirm failures**

```bash
pytest tests/test_sync.py -v
```

Expected: `404 Not Found` — route not registered yet.

- [ ] **Step 3: Create `server/routers/sync.py`**

```python
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from database import get_db
from models import Event
from schemas import SyncRequest, SyncResponse

router = APIRouter()


@router.post("/api/sync", response_model=SyncResponse)
def sync_events(request: SyncRequest, db: Session = Depends(get_db)):
    inserted = 0
    skipped = 0
    for event in request.events:
        stmt = (
            sqlite_insert(Event)
            .values(
                computer=request.computer,
                timestamp=event.timestamp,
                action=event.action,
                is_work=True,
            )
            .on_conflict_do_nothing(index_elements=["computer", "timestamp", "action"])
        )
        result = db.execute(stmt)
        if result.rowcount > 0:
            inserted += 1
        else:
            skipped += 1
    db.commit()
    return SyncResponse(inserted=inserted, skipped=skipped)
```

- [ ] **Step 4: Register the router in `server/main.py`**

Replace `server/main.py` with:

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from database import engine, Base, SessionLocal
from models import Settings
from routers import sync


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    defaults = {
        "weekly_target_hours": "40",
        "daily_target_hours":  "8",
        "tracking_start_date": "2026-01-01",
    }
    for key, value in defaults.items():
        if not db.query(Settings).filter(Settings.key == key).first():
            db.add(Settings(key=key, value=value))
    db.commit()
    db.close()
    yield


app = FastAPI(title="Work Time Tracker", lifespan=lifespan)
app.include_router(sync.router)
app.mount("/", StaticFiles(directory="static", html=True), name="static")
```

- [ ] **Step 5: Run tests**

```bash
pytest tests/test_sync.py -v
```

Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add server/routers/sync.py server/main.py tests/test_sync.py
git commit -m "feat: POST /api/sync with upsert deduplication"
```

---

## Task 8: Summary — Today & Week Endpoints

**Files:**
- Create: `server/routers/summary.py`
- Create: `tests/test_summary.py`
- Modify: `server/main.py`

- [ ] **Step 1: Write failing tests for `/api/summary/today` and `/api/summary/week`**

Create `tests/test_summary.py`:

```python
import pytest
from freezegun import freeze_time


def seed_events(client, computer, events):
    client.post("/api/sync", json={"computer": computer, "events": events})


@freeze_time("2026-05-20 14:00:00")
def test_today_empty(client):
    resp = client.get("/api/summary/today")
    assert resp.status_code == 200
    assert resp.json()["hours_worked"] == 0.0
    assert resp.json()["sessions"] == []


@freeze_time("2026-05-20 14:00:00")
def test_today_with_completed_session(client):
    seed_events(client, "ubuntu", [
        {"timestamp": "2026-05-20T08:00:00", "action": "login"},
        {"timestamp": "2026-05-20T12:00:00", "action": "logout"},
    ])
    resp = client.get("/api/summary/today")
    data = resp.json()
    assert data["hours_worked"] == pytest.approx(4.0)
    assert len(data["sessions"]) == 1
    assert data["sessions"][0]["is_active"] is False


@freeze_time("2026-05-20 14:00:00")
def test_today_open_session(client):
    # Logged in at 10am, now=14:00 → 4h worked, session still active
    seed_events(client, "ubuntu", [
        {"timestamp": "2026-05-20T10:00:00", "action": "login"},
    ])
    resp = client.get("/api/summary/today")
    data = resp.json()
    assert data["hours_worked"] == pytest.approx(4.0)
    assert data["sessions"][0]["is_active"] is True
    assert data["sessions"][0]["logout_at"] is None


@freeze_time("2026-05-20 14:00:00")
def test_today_two_computers_overlap_merged(client):
    # Ubuntu 8–12, Windows 10–14 → 6h merged total; ubuntu=4h, windows=4h separate
    seed_events(client, "ubuntu",  [
        {"timestamp": "2026-05-20T08:00:00", "action": "login"},
        {"timestamp": "2026-05-20T12:00:00", "action": "logout"},
    ])
    seed_events(client, "windows", [
        {"timestamp": "2026-05-20T10:00:00", "action": "login"},
        {"timestamp": "2026-05-20T14:00:00", "action": "logout"},
    ])
    resp = client.get("/api/summary/today")
    data = resp.json()
    assert data["hours_worked"] == pytest.approx(6.0)
    assert data["per_computer"]["ubuntu"]  == pytest.approx(4.0)
    assert data["per_computer"]["windows"] == pytest.approx(4.0)


@freeze_time("2026-05-20 14:00:00")
def test_week_summary(client):
    seed_events(client, "ubuntu", [
        {"timestamp": "2026-05-18T09:00:00", "action": "login"},
        {"timestamp": "2026-05-18T17:00:00", "action": "logout"},
        {"timestamp": "2026-05-19T09:00:00", "action": "login"},
        {"timestamp": "2026-05-19T17:00:00", "action": "logout"},
    ])
    resp = client.get("/api/summary/week")
    data = resp.json()
    assert data["total_hours"] == pytest.approx(16.0)
    assert len(data["daily_breakdown"]) >= 2
```

- [ ] **Step 2: Run to confirm failures**

```bash
pytest tests/test_summary.py -v
```

Expected: `404 Not Found` — routes not registered.

- [ ] **Step 3: Create `server/routers/summary.py`**

```python
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
```

- [ ] **Step 4: Register router in `server/main.py`**

Add `from routers import sync, summary` and `app.include_router(summary.router)` to `server/main.py`.

- [ ] **Step 5: Run tests**

```bash
pytest tests/test_summary.py -v
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add server/routers/summary.py server/main.py tests/test_summary.py
git commit -m "feat: GET /api/summary/today and /api/summary/week endpoints"
```

---

## Task 9: Summary — Daily & Weekly Aggregates

**Files:**
- Modify: `server/routers/summary.py`
- Modify: `tests/test_summary.py`

- [ ] **Step 1: Add failing tests**

Append to `tests/test_summary.py`:

```python
@freeze_time("2026-05-20 14:00:00")
def test_daily_summary_returns_requested_days(client):
    seed_events(client, "ubuntu", [
        {"timestamp": "2026-05-18T09:00:00", "action": "login"},
        {"timestamp": "2026-05-18T17:00:00", "action": "logout"},
    ])
    resp = client.get("/api/summary/daily?days=5")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["days"]) == 5
    may18 = next(d for d in data["days"] if d["date"] == "2026-05-18")
    assert may18["hours"] == pytest.approx(8.0)


@freeze_time("2026-05-20 14:00:00")
def test_daily_summary_longest_break(client):
    seed_events(client, "ubuntu", [
        {"timestamp": "2026-05-18T08:00:00", "action": "login"},
        {"timestamp": "2026-05-18T12:00:00", "action": "logout"},
        {"timestamp": "2026-05-18T13:30:00", "action": "login"},
        {"timestamp": "2026-05-18T17:00:00", "action": "logout"},
    ])
    resp = client.get("/api/summary/daily?days=5")
    may18 = next(d for d in resp.json()["days"] if d["date"] == "2026-05-18")
    assert may18["longest_break_hours"] == pytest.approx(1.5)
    assert may18["session_count"] == 2


@freeze_time("2026-05-20 14:00:00")
def test_weekly_summary(client):
    seed_events(client, "ubuntu", [
        {"timestamp": "2026-05-18T09:00:00", "action": "login"},
        {"timestamp": "2026-05-18T17:00:00", "action": "logout"},
    ])
    resp = client.get("/api/summary/weekly?weeks=4")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["weeks"]) == 4
    current_week = data["weeks"][-1]
    assert current_week["total_hours"] == pytest.approx(8.0)
```

- [ ] **Step 2: Run to confirm failures**

```bash
pytest tests/test_summary.py::test_daily_summary_returns_requested_days tests/test_summary.py::test_weekly_summary -v
```

Expected: `404 Not Found`.

- [ ] **Step 3: Add two endpoints to `server/routers/summary.py`**

Append to `server/routers/summary.py`:

```python
def _longest_break(events: list, now: datetime) -> float:
    """Find the longest gap between sessions for a single day's events."""
    all_sessions = []
    for computer in {e.computer for e in events}:
        comp_events = [e for e in events if e.computer == computer]
        all_sessions.extend(get_sessions(comp_events, now))
    if len(all_sessions) < 2:
        return 0.0
    sorted_sessions = sorted(all_sessions, key=lambda s: s[0])
    max_gap = 0.0
    for i in range(1, len(sorted_sessions)):
        gap = (sorted_sessions[i][0] - sorted_sessions[i - 1][1]).total_seconds() / 3600
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
        hours = calculate_work_hours(d_events, d_manual, now)
        sessions_count = sum(
            len(get_sessions([e for e in d_events if e.computer == c], now))
            for c in {e.computer for e in d_events}
        )
        result.append(DayStats(
            date=d,
            hours=round(hours, 2),
            session_count=sessions_count,
            longest_break_hours=_longest_break(d_events, now),
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
        cap = now if we >= today else datetime.combine(we + timedelta(days=1), datetime.min.time())
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
```

- [ ] **Step 4: Run all summary tests**

```bash
pytest tests/test_summary.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add server/routers/summary.py tests/test_summary.py
git commit -m "feat: GET /api/summary/daily and /api/summary/weekly endpoints"
```

---

## Task 10: Sessions Endpoint

**Files:**
- Create: `server/routers/sessions.py`
- Create: `tests/test_sessions.py`
- Modify: `server/main.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_sessions.py`:

```python
import pytest
from freezegun import freeze_time


def seed(client, computer, events):
    client.post("/api/sync", json={"computer": computer, "events": events})


def test_sessions_empty(client):
    resp = client.get("/api/sessions")
    assert resp.status_code == 200
    assert resp.json()["sessions"] == []
    assert resp.json()["total"] == 0


@freeze_time("2026-05-20 17:00:00")
def test_sessions_lists_paired_events(client):
    seed(client, "ubuntu", [
        {"timestamp": "2026-05-20T08:00:00", "action": "login"},
        {"timestamp": "2026-05-20T12:00:00", "action": "logout"},
    ])
    resp = client.get("/api/sessions")
    data = resp.json()
    assert data["total"] == 1
    s = data["sessions"][0]
    assert s["computer"] == "ubuntu"
    assert s["duration_hours"] == pytest.approx(4.0)
    assert s["is_work"] is True
    assert s["is_active"] is False


@freeze_time("2026-05-20 17:00:00")
def test_patch_session_toggles_is_work(client):
    seed(client, "ubuntu", [
        {"timestamp": "2026-05-20T08:00:00", "action": "login"},
        {"timestamp": "2026-05-20T12:00:00", "action": "logout"},
    ])
    session_id = client.get("/api/sessions").json()["sessions"][0]["id"]
    resp = client.patch(f"/api/sessions/{session_id}", json={"is_work": False})
    assert resp.status_code == 200
    assert resp.json()["is_work"] is False


@freeze_time("2026-05-20 17:00:00")
def test_patch_session_saves_note(client):
    seed(client, "ubuntu", [
        {"timestamp": "2026-05-20T08:00:00", "action": "login"},
        {"timestamp": "2026-05-20T12:00:00", "action": "logout"},
    ])
    session_id = client.get("/api/sessions").json()["sessions"][0]["id"]
    resp = client.patch(f"/api/sessions/{session_id}", json={"is_work": False, "note": "watching a show"})
    assert resp.status_code == 200
    assert resp.json()["note"] == "watching a show"
    assert resp.json()["is_work"] is False


def test_patch_nonexistent_session_returns_404(client):
    resp = client.patch("/api/sessions/9999", json={"is_work": False})
    assert resp.status_code == 404


@freeze_time("2026-05-20 17:00:00")
def test_sessions_pagination(client):
    events = []
    for h in range(0, 20, 2):
        events.append({"timestamp": f"2026-05-01T{h:02d}:00:00", "action": "login"})
        events.append({"timestamp": f"2026-05-01T{h+1:02d}:00:00", "action": "logout"})
    seed(client, "ubuntu", events)
    resp = client.get("/api/sessions?page=1&per_page=5")
    data = resp.json()
    assert data["total"] == 10
    assert len(data["sessions"]) == 5
    assert data["page"] == 1
```

- [ ] **Step 2: Run to confirm failures**

```bash
pytest tests/test_sessions.py -v
```

Expected: `404 Not Found`.

- [ ] **Step 3: Create `server/routers/sessions.py`**

```python
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import Event
from schemas import SessionOut, SessionsResponse, PatchSession
from session_utils import build_sessions

router = APIRouter()


@router.get("/api/sessions", response_model=SessionsResponse)
def list_sessions(
    page: int = 1,
    per_page: int = 50,
    db: Session = Depends(get_db),
):
    now = datetime.now()
    all_events = db.query(Event).order_by(Event.timestamp).all()
    sessions = build_sessions(all_events, now)
    total = len(sessions)
    start = (page - 1) * per_page
    return SessionsResponse(
        sessions=sessions[start: start + per_page],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.patch("/api/sessions/{login_event_id}", response_model=SessionOut)
def patch_session(
    login_event_id: int,
    body: PatchSession,
    db: Session = Depends(get_db),
):
    now = datetime.now()
    event = db.query(Event).filter(
        Event.id == login_event_id,
        Event.action == "login",
    ).first()
    if not event:
        raise HTTPException(status_code=404, detail="Session not found")

    event.is_work = body.is_work
    event.note = body.note
    db.commit()

    all_events = db.query(Event).filter(Event.computer == event.computer).all()
    sessions = build_sessions(all_events, now)
    session = next((s for s in sessions if s.id == login_event_id), None)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found after update")
    return session
```

- [ ] **Step 4: Register router in `server/main.py`**

Add `from routers import sync, summary, sessions` and `app.include_router(sessions.router)`.

- [ ] **Step 5: Run tests**

```bash
pytest tests/test_sessions.py -v
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add server/routers/sessions.py server/main.py tests/test_sessions.py
git commit -m "feat: GET /api/sessions with pagination and PATCH is_work toggle"
```

---

## Task 11: Manual Entries & Settings Endpoints

**Files:**
- Create: `server/routers/manual.py`
- Create: `tests/test_manual.py`
- Modify: `server/main.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_manual.py`:

```python
import pytest


def test_add_manual_entry(client):
    resp = client.post("/api/manual", json={"date": "2026-01-01", "hours": 8.0, "note": "New Years Day"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["date"] == "2026-01-01"
    assert data["hours"] == 8.0
    assert data["note"] == "New Years Day"
    assert "id" in data


def test_add_manual_entry_defaults_to_8_hours(client):
    resp = client.post("/api/manual", json={"date": "2026-07-04"})
    assert resp.status_code == 200
    assert resp.json()["hours"] == 8.0


def test_delete_manual_entry(client):
    create_resp = client.post("/api/manual", json={"date": "2026-01-01", "hours": 8.0})
    entry_id = create_resp.json()["id"]
    resp = client.delete(f"/api/manual/{entry_id}")
    assert resp.status_code == 200
    list_resp = client.get("/api/manual")
    assert all(e["id"] != entry_id for e in list_resp.json())


def test_delete_nonexistent_returns_404(client):
    resp = client.delete("/api/manual/9999")
    assert resp.status_code == 404


def test_list_manual_entries(client):
    client.post("/api/manual", json={"date": "2026-01-01", "hours": 8.0, "note": "New Years"})
    client.post("/api/manual", json={"date": "2026-07-04", "hours": 8.0, "note": "Independence Day"})
    resp = client.get("/api/manual")
    assert len(resp.json()) == 2


def test_get_settings(client):
    resp = client.get("/api/settings")
    assert resp.status_code == 200
    data = resp.json()
    assert data["weekly_target_hours"] == 40.0
    assert data["daily_target_hours"] == 8.0
    assert data["tracking_start_date"] == "2026-01-01"


def test_update_settings(client):
    resp = client.put("/api/settings", json={"weekly_target_hours": 35.0})
    assert resp.status_code == 200
    assert resp.json()["weekly_target_hours"] == 35.0
    # Other settings unchanged
    assert resp.json()["daily_target_hours"] == 8.0
```

- [ ] **Step 2: Run to confirm failures**

```bash
pytest tests/test_manual.py -v
```

Expected: `404 Not Found`.

- [ ] **Step 3: Create `server/routers/manual.py`**

```python
from datetime import date
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import ManualEntry, Settings
from schemas import ManualEntryIn, ManualEntryOut, SettingsOut, SettingsIn

router = APIRouter()


@router.get("/api/manual", response_model=list[ManualEntryOut])
def list_manual(db: Session = Depends(get_db)):
    return db.query(ManualEntry).order_by(ManualEntry.date.desc()).all()


@router.post("/api/manual", response_model=ManualEntryOut)
def add_manual(body: ManualEntryIn, db: Session = Depends(get_db)):
    entry = ManualEntry(date=body.date, hours=body.hours, note=body.note)
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@router.delete("/api/manual/{entry_id}")
def delete_manual(entry_id: int, db: Session = Depends(get_db)):
    entry = db.query(ManualEntry).filter(ManualEntry.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    db.delete(entry)
    db.commit()
    return {"ok": True}


@router.get("/api/settings", response_model=SettingsOut)
def get_settings(db: Session = Depends(get_db)):
    rows = {s.key: s.value for s in db.query(Settings).all()}
    return SettingsOut(
        weekly_target_hours=float(rows.get("weekly_target_hours", "40")),
        daily_target_hours=float(rows.get("daily_target_hours", "8")),
        tracking_start_date=date.fromisoformat(rows.get("tracking_start_date", "2026-01-01")),
    )


@router.put("/api/settings", response_model=SettingsOut)
def update_settings(body: SettingsIn, db: Session = Depends(get_db)):
    updates = {}
    if body.weekly_target_hours is not None:
        updates["weekly_target_hours"] = str(body.weekly_target_hours)
    if body.daily_target_hours is not None:
        updates["daily_target_hours"] = str(body.daily_target_hours)
    if body.tracking_start_date is not None:
        updates["tracking_start_date"] = body.tracking_start_date.isoformat()
    for key, value in updates.items():
        row = db.query(Settings).filter(Settings.key == key).first()
        if row:
            row.value = value
        else:
            db.add(Settings(key=key, value=value))
    db.commit()
    return get_settings(db)
```

- [ ] **Step 4: Register router in `server/main.py`**

Final `server/main.py`:

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from database import engine, Base, SessionLocal
from models import Settings
from routers import sync, summary, sessions, manual


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    defaults = {
        "weekly_target_hours": "40",
        "daily_target_hours":  "8",
        "tracking_start_date": "2026-01-01",
    }
    for key, value in defaults.items():
        if not db.query(Settings).filter(Settings.key == key).first():
            db.add(Settings(key=key, value=value))
    db.commit()
    db.close()
    yield


app = FastAPI(title="Work Time Tracker", lifespan=lifespan)
app.include_router(sync.router)
app.include_router(summary.router)
app.include_router(sessions.router)
app.include_router(manual.router)
app.mount("/", StaticFiles(directory="static", html=True), name="static")
```

- [ ] **Step 5: Run all tests**

```bash
pytest tests/test_manual.py -v
```

Expected: all pass.

- [ ] **Step 6: Run the full test suite**

```bash
pytest -v
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add server/routers/manual.py server/main.py tests/test_manual.py
git commit -m "feat: manual entries and settings endpoints — all API routes complete"
```

---

## Task 12: Docker Smoke Test

**Files:**
- No new files — verify the full container builds and responds.

- [ ] **Step 1: Build the Docker image**

```bash
cd ~/projects/personal/worktime-tracker
docker compose build
```

Expected: `Successfully built ...` with no errors.

- [ ] **Step 2: Start the container**

```bash
docker compose up -d
```

Expected: container starts, `docker compose ps` shows `running`.

- [ ] **Step 3: Smoke test the API**

```bash
curl -s http://localhost:8000/api/settings | python3 -m json.tool
```

Expected output:
```json
{
    "weekly_target_hours": 40.0,
    "daily_target_hours": 8.0,
    "tracking_start_date": "2026-01-01"
}
```

- [ ] **Step 4: Post a test sync and verify today summary**

```bash
curl -s -X POST http://localhost:8000/api/sync \
  -H "Content-Type: application/json" \
  -d '{"computer":"ubuntu","events":[{"timestamp":"'"$(date -Iseconds)"'","action":"login"}]}' \
  | python3 -m json.tool

curl -s http://localhost:8000/api/summary/today | python3 -m json.tool
```

Expected: sync returns `{"inserted":1,"skipped":0}`, today summary shows `hours_worked > 0` and a non-null `stop_time`.

- [ ] **Step 5: Stop the container**

```bash
docker compose down
```

- [ ] **Step 6: Final commit**

```bash
git add .
git commit -m "chore: verified Docker build and smoke test — server plan complete"
```

---

## What's Next

This plan is complete when all 12 tasks are done and `pytest` passes. The next plans are:

1. **Web UI plan** — Dashboard, Daily View, Weekly View, Log page (uses this API)
2. **Ubuntu agent plan** — `sync.py` + systemd service/timer
3. **Windows agent plan** — `sync.ps1` + Task Scheduler installer
