# Weekly Drill-Down Design

**Date:** 2026-05-30

## Overview

Add two-level expand/collapse drill-down to the weekly view. Clicking a week row fetches and shows per-day stats; clicking a day row within that expands to show individual sessions with full interactivity (work/non-work toggle, note editing).

## Goals

- Let the user inspect any historical week's days and sessions without leaving the weekly view
- Scale indefinitely — one week's worth of data fetched per expand, regardless of total history size
- Match the interaction pattern and session editing already present in the daily view

## New API Endpoint

`GET /api/summary/week/{week_start}`

`week_start` is an ISO date string (e.g. `2026-05-25`, always a Monday).

### Response schema

```json
{
  "week_start": "2026-05-25",
  "days": [
    {
      "date": "2026-05-25",
      "hours": 7.5,
      "session_count": 3,
      "longest_break_hours": 1.2,
      "is_invalid": false,
      "sessions": [
        {
          "id": 1,
          "login_at": "2026-05-25T08:00:00",
          "logout_at": "2026-05-25T12:00:00",
          "duration_hours": 4.0,
          "is_work": true,
          "is_active": false,
          "computer": "work-laptop",
          "note": null
        }
      ],
      "manual_entries": [
        {
          "id": 5,
          "hours": 1.0,
          "note": "lunch meeting"
        }
      ]
    }
  ]
}
```

Only days up to and including today are included. Uses existing `build_sessions()`, `calculate_work_hours_in_window()`, and `_longest_break_in_window()` — no new calculation logic.

## UI Structure

The weekly table gains an expand arrow column (first column, matching the daily view). Each week row is clickable. Expanding a week fetches the endpoint above and renders a nested day table inline below the week row.

```
▸  Week of May 25    38.5h    7.7h/day    −1.5h
   ┌──────────────────────────────────────────────┐
   │ ▸  Mon May 25   7.5h   3 sessions            │
   │    ┌─────────────────────────────────────────┤
   │    │  8:00 – 12:00   4.0h   work-laptop      │
   │    │  [Work] badge   note field…             │
   │    └─────────────────────────────────────────┤
   │ ▸  Tue May 26   8.0h   2 sessions            │
   │        Wed May 27   —      0 sessions        │
   └──────────────────────────────────────────────┘
▸  Week of May 18    40.1h   ...
```

Day rows with no sessions show no arrow and are not clickable. Expanded day session rows are visually and functionally identical to the daily view: same time range, duration, computer, work/non-work badge toggle, and note input with blur-to-save.

## Data Loading

- Data is fetched **lazily** — only when a week row is expanded for the first time.
- Fetched week data is cached in an in-memory `Map` keyed by `week_start` string.
- Re-opening a previously expanded week uses the cache (no re-fetch).
- Cache is not persisted across page loads (in-memory only, scoped to the tab session).
- Work/non-work toggle and note save use the existing `PATCH /api/sessions/{id}` endpoint, same as the daily view.

## Files Changed

| File | Change |
|------|--------|
| `server/schemas.py` | Add `DayDetail` and `WeekDetail` response schemas |
| `server/routers/summary.py` | Add `GET /api/summary/week/{week_start}` route |
| `server/static/js/api.js` | Add `getWeekDetail(weekStart)` method |
| `server/static/index.html` | Add arrow `<th>` to weekly table header |
| `server/static/js/weekly.js` | Add expand logic, nested day table rendering, session rows with toggle + note editing |

No changes to `daily.js` or any other files.

## Out of Scope

- Pagination or infinite scroll for the weekly list
- Adding manual entries from the weekly drill-down
- Persisting expand state across page loads
