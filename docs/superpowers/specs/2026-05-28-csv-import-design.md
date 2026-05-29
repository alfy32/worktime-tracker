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

## Output: Markdown Review Document

The script writes a single Markdown file (`import_preview.md`) with two sections.

### Section 1 — Human-readable preview

Grouped by week, then by day:

````markdown
## Week of Mon 2025-12-29 — 38.5h total

### Thu 2026-01-01 — 8.0h
| Type | Start | End | Hours | Note |
|------|-------|-----|-------|------|
| MANUAL | 12:00 AM | 8:00 AM | 8.0h | New Years Day |

### Fri 2026-01-02 — 6.8h
| Type | Start | End | Hours | Note |
|------|-------|-----|-------|------|
| EVENT | 8:21 AM | 11:54 AM | 3.6h | |
| EVENT | 1:01 PM | 4:14 PM | 3.2h | |

### Mon 2026-01-05 — 7.8h
| Type | Start | End | Hours | Note |
|------|-------|-----|-------|------|
| EVENT | 7:44 AM | 11:53 AM | 4.1h | |
| EVENT | 12:31 PM | 1:24 PM | 0.9h | |
| EVENT | 1:24 PM | 4:11 PM | 2.8h | |
| ⚠️ WARNING | unpaired login at 12:34 PM — no matching logout | | | |

### Sat 2026-01-10 — 0.0h
| ⚠️ WARNING | no sessions | | | |
````

- Week headers (`##`) show the Monday that starts the ISO week and the total hours.
- Day headers (`###`) show the three-letter weekday, date, and total hours for the day.
- Tables show one row per session or warning.
- `MANUAL` rows include the comment in the Note column.
- `⚠️ WARNING` rows flag anomalies: unpaired events, unexpected data shapes.

### Section 2 — Import payload

At the end of the file, a fenced JSON block containing the full structured import data, ready to POST:

````markdown
## Import Payload

```json
{
  "computer": "alan-windows",
  "sync_batches": [
    {
      "date": "2026-01-02",
      "events": [
        {"timestamp": "2026-01-02T08:21:41", "action": "login"},
        {"timestamp": "2026-01-02T11:54:50", "action": "logout"},
        {"timestamp": "2026-01-02T13:01:05", "action": "login"},
        {"timestamp": "2026-01-02T16:14:02", "action": "logout"}
      ]
    }
  ],
  "manual_entries": [
    {"date": "2026-01-01", "hours": 8.0, "note": "New Years Day"}
  ],
  "warnings": [
    "2026-01-05: unpaired login at 12:34 PM — no matching logout"
  ]
}
```
````

Warnings are included in the payload for reference but are never POSTed. When importing, the script reads this JSON block and sends:
- Each `sync_batches` entry to `POST /api/sync`
- Each `manual_entries` entry to `POST /api/manual`

---

## CLI Interface

```
python import_worktime.py <csv_file> [--out import_preview.md]
```

| Flag       | Default               | Purpose                          |
|------------|-----------------------|----------------------------------|
| `csv_file` | (required)            | Path to the exported CSV         |
| `--out`    | `import_preview.md`   | Path to write the Markdown output|

There is no `--import` flag. The workflow is:
1. Run the script to generate `import_preview.md`
2. Review the Markdown
3. Claude reads the Import Payload JSON block and POSTs directly to the server

---

## File Location

Script lives at the repo root: `import_worktime.py`. It is a standalone script with no new dependencies beyond the Python standard library (`csv`, `datetime`, `collections`, `argparse`) and `requests` (already used by the Ubuntu agent).

---

## Out of Scope

- Updating `tracking_start_date` — user handles this manually via Settings if needed.
- Importing `is_work = false` flags — all imported events default to `is_work = true`.
- Handling CSVs with a header row — assumed no header; if the first row looks like a header it should be skipped with a warning.
