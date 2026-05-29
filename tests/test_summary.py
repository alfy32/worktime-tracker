import pytest
from freezegun import freeze_time


def seed_events(client, computer, events):
    client.post("/api/sync", json={"computer": computer, "events": events})


@freeze_time("2026-05-20 14:00:00")
def test_today_empty(client):
    resp = client.get("/api/summary/today")
    assert resp.status_code == 200
    assert resp.json()["hours_worked"] == 0.0
    assert resp.json()["sessions"] == []


@freeze_time("2026-05-20 14:00:00")
def test_today_with_completed_session(client):
    seed_events(client, "ubuntu", [
        {"timestamp": "2026-05-20T08:00:00", "action": "login"},
        {"timestamp": "2026-05-20T12:00:00", "action": "logout"},
    ])
    resp = client.get("/api/summary/today")
    data = resp.json()
    assert data["hours_worked"] == pytest.approx(4.0)
    assert len(data["sessions"]) == 1
    assert data["sessions"][0]["is_active"] is False


@freeze_time("2026-05-20 14:00:00")
def test_today_open_session(client):
    # Logged in at 10am, now=14:00 → 4h worked, session still active
    seed_events(client, "ubuntu", [
        {"timestamp": "2026-05-20T10:00:00", "action": "login"},
    ])
    resp = client.get("/api/summary/today")
    data = resp.json()
    assert data["hours_worked"] == pytest.approx(4.0)
    assert data["sessions"][0]["is_active"] is True
    assert data["sessions"][0]["logout_at"] is None


@freeze_time("2026-05-20 14:00:00")
def test_today_two_computers_overlap_merged(client):
    # Ubuntu 8–12, Windows 10–14 → 6h merged total; ubuntu=4h, windows=4h separate
    seed_events(client, "ubuntu",  [
        {"timestamp": "2026-05-20T08:00:00", "action": "login"},
        {"timestamp": "2026-05-20T12:00:00", "action": "logout"},
    ])
    seed_events(client, "windows", [
        {"timestamp": "2026-05-20T10:00:00", "action": "login"},
        {"timestamp": "2026-05-20T14:00:00", "action": "logout"},
    ])
    resp = client.get("/api/summary/today")
    data = resp.json()
    assert data["hours_worked"] == pytest.approx(6.0)
    assert data["per_computer"]["ubuntu"]  == pytest.approx(4.0)
    assert data["per_computer"]["windows"] == pytest.approx(4.0)


@freeze_time("2026-05-20 14:00:00")
def test_week_summary(client):
    seed_events(client, "ubuntu", [
        {"timestamp": "2026-05-18T09:00:00", "action": "login"},
        {"timestamp": "2026-05-18T17:00:00", "action": "logout"},
        {"timestamp": "2026-05-19T09:00:00", "action": "login"},
        {"timestamp": "2026-05-19T17:00:00", "action": "logout"},
    ])
    resp = client.get("/api/summary/week")
    data = resp.json()
    assert data["total_hours"] == pytest.approx(16.0)
    assert len(data["daily_breakdown"]) >= 2


@freeze_time("2026-05-20 14:00:00")
def test_daily_summary_returns_requested_days(client):
    seed_events(client, "ubuntu", [
        {"timestamp": "2026-05-18T09:00:00", "action": "login"},
        {"timestamp": "2026-05-18T17:00:00", "action": "logout"},
    ])
    resp = client.get("/api/summary/daily?days=5")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["days"]) == 5
    may18 = next(d for d in data["days"] if d["date"] == "2026-05-18")
    assert may18["hours"] == pytest.approx(8.0)


@freeze_time("2026-05-20 14:00:00")
def test_daily_summary_longest_break(client):
    seed_events(client, "ubuntu", [
        {"timestamp": "2026-05-18T08:00:00", "action": "login"},
        {"timestamp": "2026-05-18T12:00:00", "action": "logout"},
        {"timestamp": "2026-05-18T13:30:00", "action": "login"},
        {"timestamp": "2026-05-18T17:00:00", "action": "logout"},
    ])
    resp = client.get("/api/summary/daily?days=5")
    may18 = next(d for d in resp.json()["days"] if d["date"] == "2026-05-18")
    assert may18["longest_break_hours"] == pytest.approx(1.5)
    assert may18["session_count"] == 2


@freeze_time("2026-05-20 14:00:00")
def test_weekly_summary(client):
    seed_events(client, "ubuntu", [
        {"timestamp": "2026-05-18T09:00:00", "action": "login"},
        {"timestamp": "2026-05-18T17:00:00", "action": "logout"},
    ])
    resp = client.get("/api/summary/weekly?weeks=4")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["weeks"]) == 4
    current_week = data["weeks"][-1]
    assert current_week["total_hours"] == pytest.approx(8.0)


@freeze_time("2026-05-20 14:00:00")
def test_daily_invalid_flag_set_for_past_open_session(client):
    # May 18: one closed session (8–12) + one unclosed login (13:00, no logout)
    # Expected: is_invalid=True, hours=4.0 (only the closed session counts)
    seed_events(client, "ubuntu", [
        {"timestamp": "2026-05-18T08:00:00", "action": "login"},
        {"timestamp": "2026-05-18T12:00:00", "action": "logout"},
        {"timestamp": "2026-05-18T13:00:00", "action": "login"},
    ])
    resp = client.get("/api/summary/daily?days=5")
    assert resp.status_code == 200
    may18 = next(d for d in resp.json()["days"] if d["date"] == "2026-05-18")
    assert may18["is_invalid"] is True
    assert may18["hours"] == pytest.approx(4.0)
    assert may18["session_count"] == 1  # unclosed session is not counted


@freeze_time("2026-05-20 14:00:00")
def test_daily_invalid_flag_false_when_all_sessions_closed(client):
    seed_events(client, "ubuntu", [
        {"timestamp": "2026-05-18T09:00:00", "action": "login"},
        {"timestamp": "2026-05-18T17:00:00", "action": "logout"},
    ])
    resp = client.get("/api/summary/daily?days=5")
    may18 = next(d for d in resp.json()["days"] if d["date"] == "2026-05-18")
    assert may18["is_invalid"] is False


@freeze_time("2026-05-20 14:00:00")
def test_daily_invalid_flag_false_for_today_open_session(client):
    # Today's open session is active — not invalid
    seed_events(client, "ubuntu", [
        {"timestamp": "2026-05-20T09:00:00", "action": "login"},
    ])
    resp = client.get("/api/summary/daily?days=2")
    today = next(d for d in resp.json()["days"] if d["date"] == "2026-05-20")
    assert today["is_invalid"] is False
    assert today["hours"] == pytest.approx(5.0)  # 09:00–14:00 = 5h


@freeze_time("2026-05-21 14:00:00")
def test_cross_day_session_counts_in_both_daily_and_weekly(client):
    # Login May 19 at 23:00, logout May 20 at 01:00 = 2h cross-midnight session.
    # Daily May 19 should count login-to-midnight (1h).
    # Weekly should count the full 2h.
    # Neither day should be flagged is_invalid (the session IS closed).
    seed_events(client, "ubuntu", [
        {"timestamp": "2026-05-19T23:00:00", "action": "login"},
        {"timestamp": "2026-05-20T01:00:00", "action": "logout"},
    ])
    daily_resp = client.get("/api/summary/daily?days=5")
    may19 = next(d for d in daily_resp.json()["days"] if d["date"] == "2026-05-19")
    may20 = next(d for d in daily_resp.json()["days"] if d["date"] == "2026-05-20")
    assert may19["is_invalid"] is False
    assert may20["is_invalid"] is False
    assert may19["hours"] == pytest.approx(1.0)   # 23:00–00:00
    assert may20["hours"] == pytest.approx(1.0)   # 00:00–01:00 (session clipped to May 20)

    weekly_resp = client.get("/api/summary/weekly?weeks=2")
    week_of_may18 = next(w for w in weekly_resp.json()["weeks"] if w["week_start"] == "2026-05-18")
    assert week_of_may18["total_hours"] == pytest.approx(2.0)  # full session
