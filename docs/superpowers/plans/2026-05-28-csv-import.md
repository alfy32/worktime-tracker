# CSV Import Script Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a standalone Python script that parses a historical work-session CSV, classifies rows into event pairs and manual entries, and writes a Markdown review document with an embedded JSON import payload.

**Architecture:** Single script `import_worktime.py` at the repo root with three pure functions (`parse_csv`, `pair_and_classify`, `generate_markdown`) and a thin `main()` CLI wrapper. No new server code — importing is done by Claude reading the JSON payload block and POSTing to the existing API endpoints.

**Tech Stack:** Python stdlib (`csv`, `datetime`, `collections`, `json`, `argparse`) only — no new dependencies.

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `import_worktime.py` | Create | CSV parsing, pairing/classification, markdown generation, CLI |
| `tests/test_import_worktime.py` | Create | Pytest tests for all three functions |

---

## Task 1: CSV Parsing

**Files:**
- Create: `import_worktime.py`
- Create: `tests/test_import_worktime.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_import_worktime.py`:

```python
import json
import textwrap
from pathlib import Path
from datetime import datetime
import pytest
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from import_worktime import parse_csv


def write_csv(tmp_path, content):
    p = tmp_path / "test.csv"
    p.write_text(textwrap.dedent(content))
    return str(p)


def test_parse_csv_basic(tmp_path):
    path = write_csv(tmp_path, """\
        1/2/2026,8:21:41 AM,login,3.55,
        1/2/2026,11:54:50 AM,logout,1.10,
    """)
    rows = parse_csv(path)
    assert len(rows) == 2
    assert rows[0] == {
        "timestamp": datetime(2026, 1, 2, 8, 21, 41),
        "action": "login",
        "comment": "",
    }
    assert rows[1]["action"] == "logout"


def test_parse_csv_skips_header(tmp_path):
    path = write_csv(tmp_path, """\
        Date,Time,Action,Hours,Comment
        1/2/2026,8:21:41 AM,login,3.55,
    """)
    rows = parse_csv(path)
    assert len(rows) == 1


def test_parse_csv_comment(tmp_path):
    path = write_csv(tmp_path, """\
        1/1/2026,12:00:00 AM,login,8.00,New Years Day
    """)
    rows = parse_csv(path)
    assert rows[0]["comment"] == "New Years Day"


def test_parse_csv_sorted_by_timestamp(tmp_path):
    path = write_csv(tmp_path, """\
        1/2/2026,1:00:00 PM,login,,
        1/2/2026,8:00:00 AM,login,,
    """)
    rows = parse_csv(path)
    assert rows[0]["timestamp"] < rows[1]["timestamp"]


def test_parse_csv_skips_short_rows(tmp_path):
    path = write_csv(tmp_path, """\
        1/2/2026,8:21:41 AM
        1/2/2026,8:21:41 AM,login,,
    """)
    rows = parse_csv(path)
    assert len(rows) == 1
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd /home/alan/projects/personal/worktime-tracker
python -m pytest tests/test_import_worktime.py -v 2>&1 | head -20
```

Expected: `ModuleNotFoundError: No module named 'import_worktime'`

- [ ] **Step 3: Implement `parse_csv`**

Create `import_worktime.py`:

```python
import csv
import json
import argparse
import sys
from datetime import datetime, date, timedelta
from collections import defaultdict


def parse_csv(path: str) -> list[dict]:
    rows = []
    with open(path, newline="") as f:
        reader = csv.reader(f)
        for row in reader:
            if len(row) < 3:
                continue
            date_str = row[0].strip()
            time_str = row[1].strip()
            action = row[2].strip().lower()
            comment = row[4].strip() if len(row) > 4 else ""

            if date_str.lower() == "date":
                continue
            if action not in ("login", "logout"):
                continue

            try:
                timestamp = datetime.strptime(
                    f"{date_str} {time_str}", "%m/%d/%Y %I:%M:%S %p"
                )
            except ValueError:
                continue

            rows.append({"timestamp": timestamp, "action": action, "comment": comment})

    return sorted(rows, key=lambda r: r["timestamp"])
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python -m pytest tests/test_import_worktime.py -v
```

Expected: all 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add import_worktime.py tests/test_import_worktime.py
git commit -m "feat: csv import — parse_csv with tests"
```

---

## Task 2: Pair and Classify

**Files:**
- Modify: `import_worktime.py` — add `pair_and_classify`
- Modify: `tests/test_import_worktime.py` — add pairing tests

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_import_worktime.py`:

```python
from import_worktime import pair_and_classify


def make_rows(*specs):
    """specs: (date_str, time_str, action, comment) tuples"""
    rows = []
    for date_str, time_str, action, comment in specs:
        ts = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %I:%M:%S %p")
        rows.append({"timestamp": ts, "action": action, "comment": comment})
    return sorted(rows, key=lambda r: r["timestamp"])


def test_pair_classify_event_pair():
    rows = make_rows(
        ("2026-01-02", "08:21:41 AM", "login", ""),
        ("2026-01-02", "11:54:50 AM", "logout", ""),
    )
    result = pair_and_classify(rows)
    assert len(result["days"]) == 1
    day = result["days"][0]
    assert len(day["sessions"]) == 1
    assert day["sessions"][0]["type"] == "EVENT"
    assert day["sessions"][0]["hours"] == pytest.approx(3.55, abs=0.01)
    assert len(result["sync_batches"]) == 1
    assert len(result["manual_entries"]) == 0


def test_pair_classify_manual_entry():
    rows = make_rows(
        ("2026-01-01", "12:00:00 AM", "login", "New Years Day"),
        ("2026-01-01", "08:00:00 AM", "logout", ""),
    )
    result = pair_and_classify(rows)
    day = result["days"][0]
    assert day["sessions"][0]["type"] == "MANUAL"
    assert day["sessions"][0]["note"] == "New Years Day"
    assert day["sessions"][0]["hours"] == pytest.approx(8.0, abs=0.01)
    assert len(result["manual_entries"]) == 1
    assert result["manual_entries"][0]["note"] == "New Years Day"
    assert len(result["sync_batches"]) == 0


def test_pair_classify_unpaired_login():
    rows = make_rows(
        ("2026-01-05", "07:44:05 AM", "login", ""),
        ("2026-01-05", "11:53:09 AM", "logout", ""),
        ("2026-01-05", "12:34:00 PM", "login", ""),
    )
    result = pair_and_classify(rows)
    day = result["days"][0]
    assert len(day["sessions"]) == 1
    assert len(day["warnings"]) == 1
    assert "unpaired login" in day["warnings"][0]


def test_pair_classify_unpaired_logout():
    rows = make_rows(
        ("2026-01-05", "11:53:09 AM", "logout", ""),
    )
    result = pair_and_classify(rows)
    day = result["days"][0]
    assert len(day["warnings"]) == 1
    assert "unpaired logout" in day["warnings"][0]


def test_pair_classify_multiple_days():
    rows = make_rows(
        ("2026-01-02", "08:21:41 AM", "login", ""),
        ("2026-01-02", "11:54:50 AM", "logout", ""),
        ("2026-01-05", "07:44:05 AM", "login", ""),
        ("2026-01-05", "11:53:09 AM", "logout", ""),
    )
    result = pair_and_classify(rows)
    assert len(result["days"]) == 2
    assert len(result["sync_batches"]) == 2


def test_pair_classify_day_total():
    rows = make_rows(
        ("2026-01-02", "08:21:41 AM", "login", ""),
        ("2026-01-02", "11:54:50 AM", "logout", ""),
        ("2026-01-02", "01:01:05 PM", "login", ""),
        ("2026-01-02", "04:14:02 PM", "logout", ""),
    )
    result = pair_and_classify(rows)
    assert result["days"][0]["total_hours"] == pytest.approx(6.77, abs=0.02)
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
python -m pytest tests/test_import_worktime.py -k "pair_classify" -v 2>&1 | head -20
```

Expected: `ImportError: cannot import name 'pair_and_classify'`

- [ ] **Step 3: Implement `pair_and_classify`**

Add to `import_worktime.py` after `parse_csv`:

```python
def pair_and_classify(rows: list[dict]) -> dict:
    by_date: dict[date, list[dict]] = defaultdict(list)
    for row in rows:
        by_date[row["timestamp"].date()].append(row)

    days = []
    sync_batches = []
    manual_entries = []
    all_warnings = []

    for d in sorted(by_date.keys()):
        day_rows = sorted(by_date[d], key=lambda r: r["timestamp"])
        sessions = []
        warnings = []
        day_sync_events = []

        i = 0
        while i < len(day_rows):
            row = day_rows[i]

            if row["action"] == "logout":
                warnings.append(
                    f"unpaired logout at {row['timestamp'].strftime('%-I:%M %p')}"
                )
                i += 1
                continue

            # row is a login — find next logout
            if i + 1 < len(day_rows) and day_rows[i + 1]["action"] == "logout":
                logout_row = day_rows[i + 1]
                hours = round(
                    (logout_row["timestamp"] - row["timestamp"]).total_seconds() / 3600,
                    2,
                )
                if row["comment"]:
                    sessions.append({
                        "type": "MANUAL",
                        "login": row["timestamp"],
                        "logout": logout_row["timestamp"],
                        "hours": hours,
                        "note": row["comment"],
                    })
                    manual_entries.append({
                        "date": d.isoformat(),
                        "hours": hours,
                        "note": row["comment"],
                    })
                else:
                    sessions.append({
                        "type": "EVENT",
                        "login": row["timestamp"],
                        "logout": logout_row["timestamp"],
                        "hours": hours,
                        "note": "",
                    })
                    day_sync_events.append({
                        "timestamp": row["timestamp"].isoformat(),
                        "action": "login",
                    })
                    day_sync_events.append({
                        "timestamp": logout_row["timestamp"].isoformat(),
                        "action": "logout",
                    })
                i += 2
            else:
                warnings.append(
                    f"unpaired login at {row['timestamp'].strftime('%-I:%M %p')}"
                    " — no matching logout"
                )
                i += 1

        if day_sync_events:
            sync_batches.append({"date": d.isoformat(), "events": day_sync_events})

        all_warnings.extend(f"{d}: {w}" for w in warnings)
        days.append({
            "date": d,
            "sessions": sessions,
            "warnings": warnings,
            "total_hours": round(sum(s["hours"] for s in sessions), 2),
        })

    return {
        "days": days,
        "sync_batches": sync_batches,
        "manual_entries": manual_entries,
        "warnings": all_warnings,
    }
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python -m pytest tests/test_import_worktime.py -v
```

Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add import_worktime.py tests/test_import_worktime.py
git commit -m "feat: csv import — pair_and_classify with tests"
```

---

## Task 3: Markdown Generation

**Files:**
- Modify: `import_worktime.py` — add `generate_markdown`
- Modify: `tests/test_import_worktime.py` — add markdown tests

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_import_worktime.py`:

```python
from import_worktime import generate_markdown


def test_generate_markdown_week_header():
    rows = make_rows(
        ("2026-01-05", "08:00:00 AM", "login", ""),
        ("2026-01-05", "04:00:00 PM", "logout", ""),
    )
    result = pair_and_classify(rows)
    md = generate_markdown(result)
    assert "## Week of Mon 2026-01-05" in md
    assert "8.0h total" in md


def test_generate_markdown_day_header():
    rows = make_rows(
        ("2026-01-05", "08:00:00 AM", "login", ""),
        ("2026-01-05", "04:00:00 PM", "logout", ""),
    )
    result = pair_and_classify(rows)
    md = generate_markdown(result)
    assert "### Mon 2026-01-05" in md


def test_generate_markdown_event_row():
    rows = make_rows(
        ("2026-01-02", "08:21:41 AM", "login", ""),
        ("2026-01-02", "11:54:50 AM", "logout", ""),
    )
    result = pair_and_classify(rows)
    md = generate_markdown(result)
    assert "| EVENT |" in md
    assert "8:21 AM" in md
    assert "11:54 AM" in md


def test_generate_markdown_manual_row():
    rows = make_rows(
        ("2026-01-01", "12:00:00 AM", "login", "New Years Day"),
        ("2026-01-01", "08:00:00 AM", "logout", ""),
    )
    result = pair_and_classify(rows)
    md = generate_markdown(result)
    assert "| MANUAL |" in md
    assert "New Years Day" in md


def test_generate_markdown_warning_row():
    rows = make_rows(
        ("2026-01-05", "12:34:00 PM", "login", ""),
    )
    result = pair_and_classify(rows)
    md = generate_markdown(result)
    assert "⚠️ WARNING" in md


def test_generate_markdown_import_payload():
    rows = make_rows(
        ("2026-01-02", "08:21:41 AM", "login", ""),
        ("2026-01-02", "11:54:50 AM", "logout", ""),
    )
    result = pair_and_classify(rows)
    md = generate_markdown(result)
    assert "## Import Payload" in md
    assert "```json" in md
    assert '"computer": "alan-windows"' in md
    assert '"sync_batches"' in md
    assert '"manual_entries"' in md


def test_generate_markdown_payload_is_valid_json():
    rows = make_rows(
        ("2026-01-02", "08:21:41 AM", "login", ""),
        ("2026-01-02", "11:54:50 AM", "logout", ""),
        ("2026-01-01", "12:00:00 AM", "login", "New Years Day"),
        ("2026-01-01", "08:00:00 AM", "logout", ""),
    )
    result = pair_and_classify(rows)
    md = generate_markdown(result)
    # Extract JSON block
    start = md.index("```json\n") + len("```json\n")
    end = md.index("\n```", start)
    payload = json.loads(md[start:end])
    assert "sync_batches" in payload
    assert "manual_entries" in payload
    assert payload["manual_entries"][0]["note"] == "New Years Day"
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
python -m pytest tests/test_import_worktime.py -k "generate_markdown" -v 2>&1 | head -20
```

Expected: `ImportError: cannot import name 'generate_markdown'`

- [ ] **Step 3: Implement `generate_markdown`**

Add to `import_worktime.py` after `pair_and_classify`:

```python
def _iso_week_monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def generate_markdown(result: dict, computer: str = "alan-windows") -> str:
    lines = ["# Worktime Import Preview", ""]

    weeks: dict[date, list[dict]] = defaultdict(list)
    for day in result["days"]:
        weeks[_iso_week_monday(day["date"])].append(day)

    for monday in sorted(weeks.keys()):
        week_days = weeks[monday]
        week_total = sum(d["total_hours"] for d in week_days)
        lines.append(
            f"## Week of Mon {monday.strftime('%Y-%m-%d')} — {week_total:.1f}h total"
        )
        lines.append("")

        for day in week_days:
            dow = day["date"].strftime("%a")
            lines.append(
                f"### {dow} {day['date'].strftime('%Y-%m-%d')} — {day['total_hours']:.1f}h"
            )
            lines.append("")

            if day["sessions"] or day["warnings"]:
                lines.append("| Type | Start | End | Hours | Note |")
                lines.append("|------|-------|-----|-------|------|")
                for s in day["sessions"]:
                    start = s["login"].strftime("%-I:%M %p")
                    end = s["logout"].strftime("%-I:%M %p")
                    lines.append(
                        f"| {s['type']} | {start} | {end} | {s['hours']:.1f}h | {s['note']} |"
                    )
                for w in day["warnings"]:
                    lines.append(f"| ⚠️ WARNING | {w} | | | |")
            else:
                lines.append("| ⚠️ WARNING | no sessions | | | |")

            lines.append("")

    total_event_sessions = sum(
        len(b["events"]) // 2 for b in result["sync_batches"]
    )
    lines.append(
        f"**Summary:** {len(result['days'])} days · "
        f"{total_event_sessions} event sessions · "
        f"{len(result['manual_entries'])} manual entries · "
        f"{len(result['warnings'])} warnings"
    )
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Import Payload")
    lines.append("")
    payload = {
        "computer": computer,
        "sync_batches": result["sync_batches"],
        "manual_entries": result["manual_entries"],
        "warnings": result["warnings"],
    }
    lines.append("```json")
    lines.append(json.dumps(payload, indent=2))
    lines.append("```")

    return "\n".join(lines)
```

- [ ] **Step 4: Run all tests**

```bash
python -m pytest tests/test_import_worktime.py -v
```

Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add import_worktime.py tests/test_import_worktime.py
git commit -m "feat: csv import — generate_markdown with tests"
```

---

## Task 4: CLI Wiring

**Files:**
- Modify: `import_worktime.py` — add `main()` and `if __name__ == "__main__"` block

- [ ] **Step 1: Add `main()` and entry point**

Append to `import_worktime.py`:

```python
def main():
    parser = argparse.ArgumentParser(
        description="Generate a worktime import preview from a CSV export"
    )
    parser.add_argument("csv_file", help="Path to the exported spreadsheet CSV")
    parser.add_argument(
        "--out",
        default="import_preview.md",
        help="Output Markdown file (default: import_preview.md)",
    )
    args = parser.parse_args()

    rows = parse_csv(args.csv_file)
    if not rows:
        print("No rows parsed — check that the CSV path is correct and the format matches.", file=sys.stderr)
        sys.exit(1)

    result = pair_and_classify(rows)
    markdown = generate_markdown(result)

    with open(args.out, "w") as f:
        f.write(markdown)

    total_event_sessions = sum(len(b["events"]) // 2 for b in result["sync_batches"])
    print(f"Preview written to {args.out}")
    print(f"  {len(result['days'])} days")
    print(f"  {total_event_sessions} event sessions")
    print(f"  {len(result['manual_entries'])} manual entries")
    print(f"  {len(result['warnings'])} warnings")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the full test suite one final time**

```bash
python -m pytest tests/test_import_worktime.py -v
```

Expected: all tests PASS

- [ ] **Step 3: Commit**

```bash
git add import_worktime.py
git commit -m "feat: csv import — CLI wiring and entry point"
```
