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


# ---------------------------------------------------------------------------
# pair_and_classify
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# generate_markdown
# ---------------------------------------------------------------------------
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
    start = md.index("```json\n") + len("```json\n")
    end = md.index("\n```", start)
    payload = json.loads(md[start:end])
    assert "sync_batches" in payload
    assert "manual_entries" in payload
    assert payload["manual_entries"][0]["note"] == "New Years Day"
