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
