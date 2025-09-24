from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_insufficient_data_before_three_checkins():
    uid = "u1"
    p = {
        "user_id": uid,
        "adherence": 90,
        "mood_trend": 0,
        "cravings": 10,
        "sleep_hours": 8.0,
        "isolation": 10,
    }
    r1 = client.post("/check-in", json=p)
    assert r1.status_code == 200
    assert r1.json()["state"] == "insufficient_data"
    r2 = client.post("/check-in", json=p)
    assert r2.status_code == 200
    assert r2.json()["state"] == "insufficient_data"


def test_high_risk_payload_yields_high_band_and_crisis_footer():
    uid = "u2"
    bad = {
        "user_id": uid,
        "adherence": 5,
        "mood_trend": -10,
        "cravings": 95,
        "sleep_hours": 2.0,
        "isolation": 90,
    }
    client.post("/check-in", json=bad)
    client.post("/check-in", json=bad)
    r3 = client.post("/check-in", json=bad)
    assert r3.status_code == 200
    body = r3.json()
    assert body["state"] == "ok"
    assert body["band"] == "high"
    assert "emergency" in body["footer"].lower()


def test_rate_limit_returns_429_after_rapid_calls():
    uid = "u3"
    p = {
        "user_id": uid,
        "adherence": 80,
        "mood_trend": 0,
        "cravings": 10,
        "sleep_hours": 8.0,
        "isolation": 10,
    }
    ok = 0
    hit_429 = False
    for _ in range(10):
        r = client.post("/check-in", json=p)
        if r.status_code == 429:
            hit_429 = True
            break
        ok += 1
    assert hit_429, "Expected 429 after rapid calls"


def test_consents_roundtrip():
    r = client.post(
        "/consents",
        json={"user_id": "u4", "terms_version": "2025-09", "accepted": True},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["user_id"] == "u4"
    getr = client.get("/consents/u4")
    assert getr.status_code == 200
    assert getr.json()["accepted"] is True
