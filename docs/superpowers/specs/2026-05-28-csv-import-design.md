# CSV Import Script — Design Spec

**Date:** 2026-05-28  
**Status:** Approved

---

## Overview

A one-time Python script to import historical work session data from a spreadsheet CSV into the worktime tracker. The script has two modes: **preview** (default) to review classified data before committing, and **import** to POST everything to the existing API.

---

## Input Format

CSV exported from Google Sheets with these columns (no header assumed unless confirmed):

| Column | Name    | Example              |
|--------|---------|----------------------|
| A      | Date    | `1/2/2026`           |
| B      | Time    | `8:21:41 AM`         |
| C      | Action  | `login` or `logout`  |
| D      | Hours   | `3.55`               |
| E      | Comment | `New Years Day`      |

The **Hours** column is ignored — durations are recalculated from timestamp pairs. The **Comment** column is the signal for manual entries.

---

## Classification Logic

### Step 1: Parse and sort

Parse each row into a datetime (`Date + Time`) and sort chronologically within each day.

### Step 2: Pair logins with logouts

Within each day, walk the rows in order and pair each `login` with the next `logout`. Unpaired events are flagged as warnings.

### Step 3: Classify each pair

- **Login has a non-empty Comment** → `MANUAL` entry: `{date, hours (logout − login), note (comment)}`
- **Login has no Comment** → `EVENT` pair: `{login timestamp, logout timestamp}`
- **Unpaired login** → `WARNING`, not imported
- **Unpaired logout** → `WARNING`, not imported

---

## Preview Output Format

Grouped by week, then by day. Run with no flags or `--preview`.

```
╔══ Week of Mon 2025-12-29  (38.5h total) ══════════════════╗

  Thu 2026-01-01  (8.0h)
    MANUAL  12:00 AM → 8:00 AM  (8.0h)  "New Years Day"

  Fri 2026-01-02  (6.8h)
    EVENT   8:21 AM → 11:54 AM  (3.6h)
    EVENT   1:01 PM → 4:14 PM   (3.2h)

╔══ Week of Mon 2026-01-05  (32.1h total) ══════════════════╗

  Mon 2026-01-05  (7.8h)
    EVENT   7:44 AM → 11:53 AM  (4.1h)
    EVENT   12:31 PM → 1:24 PM  (0.9h)
    EVENT   1:24 PM → 4:11 PM   (2.8h)
    WARNING unpaired login at 12:34 PM — no matching logout

  Sat 2026-01-10  (0.0h)
    WARNING no sessions
```

- Week header shows the Monday that starts the ISO week and the sum of all session hours that week.
- Day header shows three-letter weekday name, date, and total hours for that day.
- `MANUAL` lines show time range, duration, and the comment in quotes.
- `EVENT` lines show time range and duration.
- `WARNING` lines flag anomalies — unpaired events, weekend days with data, etc.
- A summary line at the end: total days, total events, total manual entries, total warnings.

---

## Import Mode

Run with `--import`. For each classified entry:

- **EVENT pairs** → batched per-day and POSTed to `POST /api/sync`:
  ```json
  {
    "computer": "alan-windows",
    "events": [
      {"timestamp": "2026-01-02T08:21:41", "action": "login"},
      {"timestamp": "2026-01-02T11:54:50", "action": "logout"}
    ]
  }
  ```
  The server upserts on `(computer, timestamp, action)` — safe to re-run.

- **MANUAL entries** → POSTed to `POST /api/manual`:
  ```json
  {"date": "2026-01-01", "hours": 8.0, "note": "New Years Day"}
  ```

- Warnings are printed but not imported.

After import, prints a summary: events inserted/skipped, manual entries created.

---

## CLI Interface

```
python import_worktime.py <csv_file> [--import] [--server http://localhost:8000]
```

| Flag       | Default                    | Purpose                        |
|------------|----------------------------|--------------------------------|
| `csv_file` | (required)                 | Path to the exported CSV       |
| `--import` | off (preview mode default) | Actually POST to the API       |
| `--server` | `http://localhost:8000`    | Base URL of the worktime server|

---

## File Location

Script lives at the repo root: `import_worktime.py`. It is a standalone script with no new dependencies beyond the Python standard library (`csv`, `datetime`, `collections`, `argparse`) and `requests` (already used by the Ubuntu agent).

---

## Out of Scope

- Updating `tracking_start_date` — user handles this manually via Settings if needed.
- Importing `is_work = false` flags — all imported events default to `is_work = true`.
- Handling CSVs with a header row — assumed no header; if the first row looks like a header it should be skipped with a warning.
