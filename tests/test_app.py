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


def test_troubleshoot_general_issue():
    """Test troubleshooting endpoint with general issue type."""
    r = client.post("/troubleshoot", json={"issue_type": "general"})
    assert r.status_code == 200
    body = r.json()
    assert body["issue_type"] == "general"
    assert "steps" in body
    assert len(body["steps"]) >= 3
    assert body["steps"][0]["step"] == 1
    assert "additional_resources" in body


def test_troubleshoot_login_issue():
    """Test troubleshooting endpoint with login issue type."""
    r = client.post("/troubleshoot", json={"issue_type": "login"})
    assert r.status_code == 200
    body = r.json()
    assert body["issue_type"] == "login"
    assert len(body["steps"]) == 5
    assert "username" in body["steps"][0]["description"].lower()
    assert "internet" in body["steps"][1]["description"].lower()


def test_troubleshoot_with_error_message():
    """Test troubleshooting endpoint with error message context."""
    r = client.post(
        "/troubleshoot",
        json={"issue_type": "connection", "error_message": "Connection timeout after 30 seconds"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["issue_type"] == "connection"

    # Should have original connection steps plus context-specific step
    assert len(body["steps"]) == 4  # 3 connection steps + 1 context step

    # Last step should reference the error message
    last_step = body["steps"][-1]
    assert "Connection timeout" in last_step["description"]


def test_troubleshoot_data_issue():
    """Test troubleshooting endpoint with data issue type."""
    r = client.post("/troubleshoot", json={"issue_type": "data"})
    assert r.status_code == 200
    body = r.json()
    assert body["issue_type"] == "data"
    assert len(body["steps"]) == 3
    assert "fields" in body["steps"][0]["description"].lower()


def test_troubleshoot_performance_issue():
    """Test troubleshooting endpoint with performance issue type."""
    r = client.post("/troubleshoot", json={"issue_type": "performance"})
    assert r.status_code == 200
    body = r.json()
    assert body["issue_type"] == "performance"
    assert len(body["steps"]) == 3
    assert "device" in body["steps"][0]["description"].lower()


def test_troubleshoot_with_long_error_message():
    """Test troubleshooting endpoint truncates very long error messages."""
    long_error = (
        "This is a very long error message that exceeds one hundred characters and should be "
        "truncated by the system to prevent overly verbose descriptions from cluttering the "
        "response"
    )

    r = client.post("/troubleshoot", json={"issue_type": "general", "error_message": long_error})
    assert r.status_code == 200
    body = r.json()

    # Should have general steps plus context step
    context_step = body["steps"][-1]
    assert "..." in context_step["description"]
    assert len(context_step["description"]) < len(long_error) + 50  # Much shorter than original
