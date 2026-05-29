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


def _iso_week_monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _fmt_duration(td: timedelta) -> str:
    total = int(td.total_seconds())
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def generate_markdown(result: dict, computer: str = "alan-windows") -> str:
    lines = ["# Worktime Import Preview", ""]

    weeks: dict[date, list[dict]] = defaultdict(list)
    for day in result["days"]:
        weeks[_iso_week_monday(day["date"])].append(day)

    for monday in sorted(weeks.keys()):
        week_days = weeks[monday]
        week_total = sum(
            (s["logout"] - s["login"] for d in week_days for s in d["sessions"]),
            timedelta(),
        )
        lines.append(
            f"## Week of Mon {monday.strftime('%Y-%m-%d')} — {_fmt_duration(week_total)} total"
        )
        lines.append("")

        for day in week_days:
            dow = day["date"].strftime("%a")
            day_total = sum(
                (s["logout"] - s["login"] for s in day["sessions"]), timedelta()
            )
            lines.append(
                f"### {dow} {day['date'].strftime('%Y-%m-%d')} — {_fmt_duration(day_total)}"
            )
            lines.append("")

            if day["sessions"] or day["warnings"]:
                lines.append("| Type | Start | End | Duration | Note |")
                lines.append("|------|-------|-----|----------|------|")
                for s in day["sessions"]:
                    start = s["login"].strftime("%-I:%M:%S %p")
                    end = s["logout"].strftime("%-I:%M:%S %p")
                    dur = _fmt_duration(s["logout"] - s["login"])
                    lines.append(
                        f"| {s['type']} | {start} | {end} | {dur} | {s['note']} |"
                    )
                for w in day["warnings"]:
                    lines.append(f"| ⚠️ WARNING | {w} | | | |")
            else:
                lines.append("| ⚠️ WARNING | no sessions | | | |")

            lines.append("")

    total_event_sessions = sum(len(b["events"]) // 2 for b in result["sync_batches"])
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
