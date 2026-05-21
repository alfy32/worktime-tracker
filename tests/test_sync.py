def test_sync_inserts_new_events(client):
    resp = client.post("/api/sync", json={
        "computer": "ubuntu",
        "events": [
            {"timestamp": "2026-05-20T08:00:00", "action": "login"},
            {"timestamp": "2026-05-20T12:00:00", "action": "logout"},
        ],
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["inserted"] == 2
    assert data["skipped"] == 0


def test_sync_skips_duplicates(client):
    payload = {
        "computer": "ubuntu",
        "events": [{"timestamp": "2026-05-20T08:00:00", "action": "login"}],
    }
    client.post("/api/sync", json=payload)
    resp = client.post("/api/sync", json=payload)
    assert resp.status_code == 200
    assert resp.json()["inserted"] == 0
    assert resp.json()["skipped"] == 1


def test_sync_partial_duplicates(client):
    client.post("/api/sync", json={
        "computer": "windows",
        "events": [{"timestamp": "2026-05-20T08:00:00", "action": "login"}],
    })
    resp = client.post("/api/sync", json={
        "computer": "windows",
        "events": [
            {"timestamp": "2026-05-20T08:00:00", "action": "login"},   # duplicate
            {"timestamp": "2026-05-20T12:00:00", "action": "logout"},  # new
        ],
    })
    assert resp.json()["inserted"] == 1
    assert resp.json()["skipped"] == 1


def test_sync_different_computers_dont_conflict(client):
    payload = {"events": [{"timestamp": "2026-05-20T08:00:00", "action": "login"}]}
    r1 = client.post("/api/sync", json={**payload, "computer": "ubuntu"})
    r2 = client.post("/api/sync", json={**payload, "computer": "windows"})
    assert r1.json()["inserted"] == 1
    assert r2.json()["inserted"] == 1
