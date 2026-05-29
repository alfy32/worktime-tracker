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
