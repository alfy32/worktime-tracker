# Invalid Session Auto-Correction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Exclude past unclosed login sessions (no matching logout) from all hour calculations and surface them as warnings in the daily detail view.

**Architecture:** A single guard in `get_sessions()` excludes unclosed logins on past days — this fix propagates automatically to all callers (bank, weekly, stop-time). A new `has_unclosed_login()` helper flags affected days so the daily API can set `is_invalid=True` on `DayStats`. The UI reads this flag to show a warning badge on the row and "never ended" on the specific session in the expanded detail.

**Tech Stack:** Python / FastAPI / SQLAlchemy (server), vanilla JS (frontend), pytest + freezegun (tests)

---

## File Map

| File | Change |
|------|--------|
| `server/calculations.py` | Fix `get_sessions`; add `has_unclosed_login` |
| `server/schemas.py` | Add `is_invalid: bool = False` to `DayStats` |
| `server/routers/summary.py` | Import `has_unclosed_login`; set `is_invalid` in `summary_daily` |
| `server/static/js/daily.js` | Warning badge on invalid rows; "never ended" on open past sessions |
| `tests/test_calculations.py` | New tests for past unclosed behaviour + `has_unclosed_login` |
| `tests/test_summary.py` | Integration tests for `is_invalid` flag |

---

### Task 1: Fix `get_sessions` to exclude past unclosed logins

**Files:**
- Modify: `server/calculations.py:22-26`
- Test: `tests/test_calculations.py`

The open-session guard at the end of `get_sessions` currently always appends a session using `now` as the end. Change it to only do so when the pending login is on the same date as `now` (i.e. today). Logins on earlier dates with no logout are silently dropped — 0 hours contributed.

- [ ] **Step 1: Write the failing test**

Add inside `class TestGetSessions` in `tests/test_calculations.py`:

```python
def test_past_unclosed_login_excluded(self):
    # Login on May 20, but now is May 21 → no session (would have been invalid)
    later_now = datetime(2026, 5, 21, 14, 0)
    events = [ev("ubuntu", "login", datetime(2026, 5, 20, 8, 0))]
    assert get_sessions(events, later_now) == []

def test_today_open_session_still_included(self):
    # Login and now are on the same date → session still counted (currently active)
    events = [ev("ubuntu", "login", datetime(2026, 5, 20, 8, 0))]
    assert get_sessions(events, NOW) == [(datetime(2026, 5, 20, 8, 0), NOW)]
```

Note: `test_today_open_session_still_included` overlaps with the existing `test_open_session_uses_now` — keep both; the second makes the intent explicit.

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd /home/alan/projects/personal/worktime-tracker
python -m pytest tests/test_calculations.py::TestGetSessions::test_past_unclosed_login_excluded -v
```

Expected: FAIL — `[(datetime(2026, 5, 20, 8, 0), datetime(2026, 5, 21, 14, 0))]` is returned instead of `[]`.

- [ ] **Step 3: Implement the fix in `server/calculations.py`**

Replace lines 23–26 (the `if pending_login` block at the end of `get_sessions`):

```python
    if pending_login is not None and pending_is_work:
        if pending_login.date() >= now.date():
            sessions.append((pending_login, now))
```

The `>=` handles the normal case (same day). A login strictly before `now.date()` is silently dropped.

- [ ] **Step 4: Run all `TestGetSessions` tests to confirm pass and no regressions**

```bash
python -m pytest tests/test_calculations.py::TestGetSessions -v
```

Expected: all PASS. The existing `test_open_session_uses_now` test still passes because its login timestamp (`2026-05-20 08:00`) is on the same date as `NOW` (`2026-05-20 14:00`).

- [ ] **Step 5: Run the full test suite to confirm no regressions**

```bash
python -m pytest tests/ -v
```

Expected: all existing tests PASS (no existing test uses a login on a day before `now`).

- [ ] **Step 6: Commit**

```bash
git add server/calculations.py tests/test_calculations.py
git commit -m "fix: exclude past unclosed login sessions from hour calculations"
```

---

### Task 2: Add `has_unclosed_login` helper

**Files:**
- Modify: `server/calculations.py` (add function after `get_sessions`)
- Test: `tests/test_calculations.py`

This helper detects whether any computer in a set of events has a login with no matching logout. It is used by `summary_daily` to flag days as invalid. It does not use `now` — it only cares about structural pairing of events.

- [ ] **Step 1: Write the failing tests**

Add a new class at the bottom of `tests/test_calculations.py`. Also add `has_unclosed_login` to the import line at the top of the file:

```python
from calculations import get_sessions, merge_intervals, calculate_work_hours, calculate_per_computer_hours
from calculations import weekdays_elapsed, calculate_hours_bank, remaining_weekdays_in_week, calculate_stop_time
from calculations import has_unclosed_login
```

```python
class TestHasUnclosedLogin:
    def test_single_unclosed_login(self):
        events = [ev("ubuntu", "login", datetime(2026, 5, 20, 8, 0))]
        assert has_unclosed_login(events) is True

    def test_closed_session_returns_false(self):
        events = [
            ev("ubuntu", "login",  datetime(2026, 5, 20, 8, 0)),
            ev("ubuntu", "logout", datetime(2026, 5, 20, 12, 0)),
        ]
        assert has_unclosed_login(events) is False

    def test_empty_events_returns_false(self):
        assert has_unclosed_login([]) is False

    def test_one_computer_closed_one_unclosed(self):
        events = [
            ev("ubuntu",  "login",  datetime(2026, 5, 20, 8, 0)),
            ev("ubuntu",  "logout", datetime(2026, 5, 20, 12, 0)),
            ev("windows", "login",  datetime(2026, 5, 20, 9, 0)),
            # windows has no logout
        ]
        assert has_unclosed_login(events) is True

    def test_multiple_sessions_all_closed(self):
        events = [
            ev("ubuntu", "login",  datetime(2026, 5, 20, 8, 0)),
            ev("ubuntu", "logout", datetime(2026, 5, 20, 12, 0)),
            ev("ubuntu", "login",  datetime(2026, 5, 20, 13, 0)),
            ev("ubuntu", "logout", datetime(2026, 5, 20, 17, 0)),
        ]
        assert has_unclosed_login(events) is False
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
python -m pytest tests/test_calculations.py::TestHasUnclosedLogin -v
```

Expected: FAIL with `ImportError: cannot import name 'has_unclosed_login'`.

- [ ] **Step 3: Implement `has_unclosed_login` in `server/calculations.py`**

Add after the `get_sessions` function (around line 27):

```python
def has_unclosed_login(events: list) -> bool:
    """Return True if any computer in events has a login with no matching logout."""
    for computer in {e.computer for e in events}:
        comp_events = sorted(
            [e for e in events if e.computer == computer],
            key=lambda e: e.timestamp,
        )
        pending = False
        for ev in comp_events:
            if ev.action == "login":
                pending = True
            elif ev.action == "logout" and pending:
                pending = False
        if pending:
            return True
    return False
```

- [ ] **Step 4: Run the new tests**

```bash
python -m pytest tests/test_calculations.py::TestHasUnclosedLogin -v
```

Expected: all PASS.

- [ ] **Step 5: Run the full test suite**

```bash
python -m pytest tests/ -v
```

Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add server/calculations.py tests/test_calculations.py
git commit -m "feat: add has_unclosed_login helper to calculations"
```

---

### Task 3: Expose `is_invalid` on the daily summary API

**Files:**
- Modify: `server/schemas.py:66-70`
- Modify: `server/routers/summary.py:14` (import) and `summary.py:196-208` (daily loop)
- Test: `tests/test_summary.py`

Add `is_invalid: bool = False` to `DayStats`. In `summary_daily`, for each past day, call `has_unclosed_login` and pass the result into `DayStats`. Today is never marked invalid regardless of open sessions.

- [ ] **Step 1: Write failing integration tests**

Add to `tests/test_summary.py`:

```python
@freeze_time("2026-05-20 14:00:00")
def test_daily_invalid_flag_set_for_past_open_session(client):
    # May 18: one closed session (8–12) + one unclosed login (13:00, no logout)
    # Expected: is_invalid=True, hours=4.0 (only the closed session counts)
    seed_events(client, "ubuntu", [
        {"timestamp": "2026-05-18T08:00:00", "action": "login"},
        {"timestamp": "2026-05-18T12:00:00", "action": "logout"},
        {"timestamp": "2026-05-18T13:00:00", "action": "login"},
    ])
    resp = client.get("/api/summary/daily?days=5")
    assert resp.status_code == 200
    may18 = next(d for d in resp.json()["days"] if d["date"] == "2026-05-18")
    assert may18["is_invalid"] is True
    assert may18["hours"] == pytest.approx(4.0)
    assert may18["session_count"] == 1  # unclosed session is not counted


@freeze_time("2026-05-20 14:00:00")
def test_daily_invalid_flag_false_when_all_sessions_closed(client):
    seed_events(client, "ubuntu", [
        {"timestamp": "2026-05-18T09:00:00", "action": "login"},
        {"timestamp": "2026-05-18T17:00:00", "action": "logout"},
    ])
    resp = client.get("/api/summary/daily?days=5")
    may18 = next(d for d in resp.json()["days"] if d["date"] == "2026-05-18")
    assert may18["is_invalid"] is False


@freeze_time("2026-05-20 14:00:00")
def test_daily_invalid_flag_false_for_today_open_session(client):
    # Today's open session is active — not invalid
    seed_events(client, "ubuntu", [
        {"timestamp": "2026-05-20T09:00:00", "action": "login"},
    ])
    resp = client.get("/api/summary/daily?days=2")
    today = next(d for d in resp.json()["days"] if d["date"] == "2026-05-20")
    assert today["is_invalid"] is False
    assert today["hours"] == pytest.approx(5.0)  # 09:00–14:00 = 5h
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
python -m pytest tests/test_summary.py::test_daily_invalid_flag_set_for_past_open_session tests/test_summary.py::test_daily_invalid_flag_false_when_all_sessions_closed tests/test_summary.py::test_daily_invalid_flag_false_for_today_open_session -v
```

Expected: FAIL — `is_invalid` key is missing from the response (field not yet on schema).

- [ ] **Step 3: Add `is_invalid` to `DayStats` in `server/schemas.py`**

Change:

```python
class DayStats(BaseModel):
    date: date
    hours: float
    session_count: int
    longest_break_hours: float
```

To:

```python
class DayStats(BaseModel):
    date: date
    hours: float
    session_count: int
    longest_break_hours: float
    is_invalid: bool = False
```

- [ ] **Step 4: Update `summary_daily` in `server/routers/summary.py`**

Add `has_unclosed_login` to the calculations import at the top of the file:

```python
from calculations import (
    calculate_work_hours, calculate_per_computer_hours,
    calculate_hours_bank, calculate_stop_time,
    get_sessions, merge_intervals, remaining_weekdays_in_week, weekdays_elapsed,
    has_unclosed_login,
)
```

Then in the `summary_daily` function, replace the `result.append(DayStats(...))` call (currently around line 202) with:

```python
        is_invalid = (d < today) and has_unclosed_login(d_events)
        result.append(DayStats(
            date=d,
            hours=round(hours, 2),
            session_count=sessions_count,
            longest_break_hours=_longest_break(d_events, cutoff),
            is_invalid=is_invalid,
        ))
```

- [ ] **Step 5: Run the new tests**

```bash
python -m pytest tests/test_summary.py::test_daily_invalid_flag_set_for_past_open_session tests/test_summary.py::test_daily_invalid_flag_false_when_all_sessions_closed tests/test_summary.py::test_daily_invalid_flag_false_for_today_open_session -v
```

Expected: all PASS.

- [ ] **Step 6: Run the full test suite**

```bash
python -m pytest tests/ -v
```

Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add server/schemas.py server/routers/summary.py tests/test_summary.py
git commit -m "feat: add is_invalid flag to DayStats for days with unclosed logins"
```

---

### Task 4: UI — warning badge on invalid day rows

**Files:**
- Modify: `server/static/js/daily.js:57-65` (`renderTable` function)

When `d.is_invalid` is true, show a small orange ⚠ icon in the hours cell before the hours value. The icon has a tooltip explaining the issue.

- [ ] **Step 1: Update `renderTable` in `server/static/js/daily.js`**

Locate the `renderTable` function. Find the hours cell line (currently around line 64):

```js
          '<td class="p-4 text-right font-semibold ' + color + '">' + (d.hours > 0 ? fmtH(d.hours) : '—') + '</td>' +
```

Replace it with:

```js
          '<td class="p-4 text-right font-semibold ' + color + '">' +
            (d.is_invalid ? '<span class="text-orange-400 mr-1" title="One or more sessions never ended">⚠</span>' : '') +
            (d.hours > 0 ? fmtH(d.hours) : '—') +
          '</td>' +
```

- [ ] **Step 2: Start the server and verify visually**

```bash
cd /home/alan/projects/personal/worktime-tracker
docker compose up -d
```

Open the app in a browser and navigate to the Daily tab. Any day in the list that has an unclosed past login should show an orange ⚠ before the hours value. Days without invalid sessions should be unchanged.

If there are no real invalid sessions in your dev data, you can temporarily insert one directly in the DB to test:

```bash
sqlite3 server/worktime.db "INSERT INTO events (computer, timestamp, action, is_work) VALUES ('test-pc', '2026-05-25T10:00:00', 'login', 1);"
```

Then reload the Daily tab and confirm the ⚠ appears on May 25.

Remove the test row when done:

```bash
sqlite3 server/worktime.db "DELETE FROM events WHERE computer = 'test-pc';"
```

- [ ] **Step 3: Commit**

```bash
git add server/static/js/daily.js
git commit -m "feat: show warning badge on daily rows with unclosed past sessions"
```

---

### Task 5: UI — "never ended" indicator in expanded session details

**Files:**
- Modify: `server/static/js/daily.js:93-113` (`toggleRow` function)

When the expanded detail for a past day shows a session with `is_active === true`, replace the duration display with a "never ended" warning and replace the "active" label in the time range with an orange warning.

- [ ] **Step 1: Update `toggleRow` in `server/static/js/daily.js`**

In `toggleRow`, the variable `dateStr` is already defined (line 93). Add `todayStr` immediately after it:

```js
    const dateStr = rows[i].date;
    const todayStr = new Date().toISOString().slice(0, 10);
    const isPastDay = dateStr < todayStr;
```

Then find the `sessionRows` map (lines 99–113). Replace the two relevant spans:

**Time range span** — change from:
```js
        '<span class="text-slate-400 shrink-0">' +
          fmtTime(s.login_at) + ' – ' + (s.logout_at ? fmtTime(s.logout_at) : '<span class="text-teal-500">active</span>') +
        '</span>' +
```
To:
```js
        '<span class="text-slate-400 shrink-0">' +
          fmtTime(s.login_at) + ' – ' + (
            s.logout_at
              ? fmtTime(s.logout_at)
              : (isPastDay
                  ? '<span class="text-orange-400">never ended</span>'
                  : '<span class="text-teal-500">active</span>')
          ) +
        '</span>' +
```

**Duration span** — change from:
```js
        '<span class="text-slate-500 shrink-0 w-10">' + fmtH(s.duration_hours) + '</span>' +
```
To:
```js
        '<span class="text-slate-500 shrink-0 w-10">' + (s.is_active && isPastDay ? '—' : fmtH(s.duration_hours)) + '</span>' +
```

This hides the nonsensical duration (days since login) and shows `—` instead.

- [ ] **Step 2: Verify visually**

With the server running, open the Daily tab and expand a day that has an invalid session (use the test row from Task 4 if needed, or check any row with a ⚠ badge). Confirm:
- The time range shows `10:00 AM – never ended` in orange (not "active" in teal).
- The duration column shows `—`.
- Other sessions on the same day (with valid logouts) display normally.
- Today's open session (if present) still shows "active" in teal with the correct duration.

- [ ] **Step 3: Commit**

```bash
git add server/static/js/daily.js
git commit -m "feat: show never-ended warning for past open sessions in daily detail"
```
