# Invalid Session Auto-Correction Design

**Date:** 2026-05-28

## Problem

A login event on a past day with no matching logout is treated as a valid session spanning from the login time to end-of-day. This inflates hours across all calculations (daily totals, weekly totals, bank, stop time). The data is corrupted silently — there is no indication to the user that something is wrong.

## Goal

- Past unclosed sessions contribute **0 hours** to all calculations.
- The daily detail view shows the invalid session with a **"Never ended" warning** so the user knows it exists.
- The daily row shows a **warning indicator** when a day contains one or more invalid sessions.

## Scope

"Invalid session" = a login event on any day before today that has no matching logout event on the same day.

Today's open session (currently active) is **not** invalid — it is expected and counted normally using `now` as the end time.

---

## Architecture

### 1. Core fix — `calculations.py::get_sessions()`

`get_sessions` currently creates an open session for any unmatched login, using `now` as the end time. The fix adds one guard: only create an open session if the login date equals `now.date()`.

```python
if pending_login is not None and pending_is_work:
    if pending_login.date() >= now.date():   # today only
        sessions.append((pending_login, now))
    # else: past unclosed login — skip, contributes 0 hours
```

Because all calculation functions funnel through `get_sessions` (via `calculate_work_hours`), this single change fixes hours across:
- `calculate_work_hours` (used by all summary endpoints)
- `calculate_hours_bank`
- `calculate_stop_time`
- `calculate_per_computer_hours`
- weekly summaries

**No other calculation functions need to change.**

The per-day case in `summary_daily` also works correctly: past days pass `cutoff = end_of_day` (midnight of `d+1`) as `now`, so `pending_login.date()` (`d`) is less than `cutoff.date()` (`d+1`) and the open session is skipped.

### 2. Detection helper — `calculations.py::has_unclosed_login()`

A new helper that checks whether any computer in a set of events has an unmatched login:

```python
def has_unclosed_login(events: list) -> bool:
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

Lives in `calculations.py` alongside `get_sessions`.

### 3. Schema — `schemas.py::DayStats`

Add one field:

```python
class DayStats(BaseModel):
    date: date
    hours: float
    session_count: int
    longest_break_hours: float
    is_invalid: bool = False   # new
```

### 4. Server — `routers/summary.py::summary_daily()`

For each past day (`d < today`), after computing hours, call `has_unclosed_login(d_events)` and set `is_invalid` on the `DayStats` result. Today is never marked invalid.

```python
is_past = d < today
is_invalid = is_past and has_unclosed_login(d_events)
result.append(DayStats(
    date=d,
    hours=round(hours, 2),
    session_count=sessions_count,
    longest_break_hours=_longest_break(d_events, cutoff),
    is_invalid=is_invalid,
))
```

### 5. Sessions display — `session_utils.py::build_sessions()`

**No change.** `build_sessions` continues to return open sessions with `is_active=True` and `logout_at=None`. This is correct — the daily detail view needs to show invalid sessions so the user can see them.

### 6. UI — `server/static/js/daily.js`

**Day row badge:** When `d.is_invalid`, render a small warning indicator in the hours cell — an orange `⚠` before the hours value.

**Expanded session row:** When rendering sessions for a past day (the row's `dateStr` is not today's date string), check if a session has `is_active === true`. If so, replace the duration span with `⚠ Never ended` in orange, and omit the `active` styling from the time range.

Today string comparison:
```js
const todayStr = new Date().toISOString().slice(0, 10);
const isPastDay = dateStr < todayStr;
```

---

## Data Flow

```
Event rows (past day, unclosed login)
  → get_sessions(events, cutoff)
      pending_login.date() < cutoff.date()  →  skipped (0 hours)
  → DayStats.hours = sum of valid sessions only
  → DayStats.is_invalid = has_unclosed_login(events) = true

Event rows (past day, unclosed login)
  → build_sessions(events, now)         ← unchanged
      SessionOut(is_active=True, logout_at=None)
  → daily.js expanded row
      isPastDay && s.is_active  →  "⚠ Never ended"
```

---

## What Is Not Changed

- `build_sessions` / `SessionOut` schema — sessions list is display-only; invalid sessions appear there intentionally.
- `session_count` in `DayStats` — counts sessions from `get_sessions` (post-fix), so invalid open sessions are **not** counted. This is consistent with hours.
- Other summary endpoints (`/today`, `/week`, `/weekly`) — fixed automatically via `get_sessions` change; no schema or endpoint changes needed.
- Manual entries — unaffected; they are always valid by definition.

---

## Error Handling

- If `d_events` is empty, `has_unclosed_login([])` returns `False` — no change to behavior.
- The fix is non-destructive: it changes what is computed, not what is stored. Invalid login events remain in the database and are visible in the detail view.

---

## Testing

- Unit test `get_sessions`: past unclosed login → no session created; today's unclosed login → session created using `now`.
- Unit test `has_unclosed_login`: returns `True` when unmatched login exists, `False` when all matched.
- Update `test_calculations.py` for changed `get_sessions` behavior.
- Integration test `summary_daily`: day with unclosed login → `hours` excludes open session, `is_invalid=True`.
- Existing tests for `calculate_work_hours`, `calculate_hours_bank`, `calculate_stop_time` — verify no regressions (open sessions on past days were previously inflating numbers in tests too, so some test fixture values may need updating).
