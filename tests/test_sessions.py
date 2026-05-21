import pytest
from freezegun import freeze_time


def seed(client, computer, events):
    client.post("/api/sync", json={"computer": computer, "events": events})


def test_sessions_empty(client):
    resp = client.get("/api/sessions")
    assert resp.status_code == 200
    assert resp.json()["sessions"] == []
    assert resp.json()["total"] == 0


@freeze_time("2026-05-20 17:00:00")
def test_sessions_lists_paired_events(client):
    seed(client, "ubuntu", [
        {"timestamp": "2026-05-20T08:00:00", "action": "login"},
        {"timestamp": "2026-05-20T12:00:00", "action": "logout"},
    ])
    resp = client.get("/api/sessions")
    data = resp.json()
    assert data["total"] == 1
    s = data["sessions"][0]
    assert s["computer"] == "ubuntu"
    assert s["duration_hours"] == pytest.approx(4.0)
    assert s["is_work"] is True
    assert s["is_active"] is False


@freeze_time("2026-05-20 17:00:00")
def test_patch_session_toggles_is_work(client):
    seed(client, "ubuntu", [
        {"timestamp": "2026-05-20T08:00:00", "action": "login"},
        {"timestamp": "2026-05-20T12:00:00", "action": "logout"},
    ])
    session_id = client.get("/api/sessions").json()["sessions"][0]["id"]
    resp = client.patch(f"/api/sessions/{session_id}", json={"is_work": False})
    assert resp.status_code == 200
    assert resp.json()["is_work"] is False


@freeze_time("2026-05-20 17:00:00")
def test_patch_session_saves_note(client):
    seed(client, "ubuntu", [
        {"timestamp": "2026-05-20T08:00:00", "action": "login"},
        {"timestamp": "2026-05-20T12:00:00", "action": "logout"},
    ])
    session_id = client.get("/api/sessions").json()["sessions"][0]["id"]
    resp = client.patch(f"/api/sessions/{session_id}", json={"is_work": False, "note": "watching a show"})
    assert resp.status_code == 200
    assert resp.json()["note"] == "watching a show"
    assert resp.json()["is_work"] is False


def test_patch_nonexistent_session_returns_404(client):
    resp = client.patch("/api/sessions/9999", json={"is_work": False})
    assert resp.status_code == 404


@freeze_time("2026-05-20 17:00:00")
def test_sessions_pagination(client):
    events = []
    for h in range(0, 20, 2):
        events.append({"timestamp": f"2026-05-01T{h:02d}:00:00", "action": "login"})
        events.append({"timestamp": f"2026-05-01T{h+1:02d}:00:00", "action": "logout"})
    seed(client, "ubuntu", events)
    resp = client.get("/api/sessions?page=1&per_page=5")
    data = resp.json()
    assert data["total"] == 10
    assert len(data["sessions"]) == 5
    assert data["page"] == 1
