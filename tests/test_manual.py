import pytest


def test_add_manual_entry(client):
    resp = client.post("/api/manual", json={"date": "2026-01-01", "hours": 8.0, "note": "New Years Day"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["date"] == "2026-01-01"
    assert data["hours"] == 8.0
    assert data["note"] == "New Years Day"
    assert "id" in data


def test_add_manual_entry_defaults_to_8_hours(client):
    resp = client.post("/api/manual", json={"date": "2026-07-04"})
    assert resp.status_code == 200
    assert resp.json()["hours"] == 8.0


def test_delete_manual_entry(client):
    create_resp = client.post("/api/manual", json={"date": "2026-01-01", "hours": 8.0})
    entry_id = create_resp.json()["id"]
    resp = client.delete(f"/api/manual/{entry_id}")
    assert resp.status_code == 200
    list_resp = client.get("/api/manual")
    assert all(e["id"] != entry_id for e in list_resp.json())


def test_delete_nonexistent_returns_404(client):
    resp = client.delete("/api/manual/9999")
    assert resp.status_code == 404


def test_list_manual_entries(client):
    client.post("/api/manual", json={"date": "2026-01-01", "hours": 8.0, "note": "New Years"})
    client.post("/api/manual", json={"date": "2026-07-04", "hours": 8.0, "note": "Independence Day"})
    resp = client.get("/api/manual")
    assert len(resp.json()) == 2


def test_get_settings(client):
    resp = client.get("/api/settings")
    assert resp.status_code == 200
    data = resp.json()
    assert data["weekly_target_hours"] == 40.0
    assert data["daily_target_hours"] == 8.0
    assert data["tracking_start_date"] == "2026-01-01"


def test_update_settings(client):
    resp = client.put("/api/settings", json={"weekly_target_hours": 35.0})
    assert resp.status_code == 200
    assert resp.json()["weekly_target_hours"] == 35.0
    # Other settings unchanged
    assert resp.json()["daily_target_hours"] == 8.0
