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
