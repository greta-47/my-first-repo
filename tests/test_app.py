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
    response_data = r1.json()
    assert response_data["state"] == "insufficient_data"
    assert "1 check-in" in response_data["reflection"]
    assert "2 more" in response_data["reflection"]

    r2 = client.post("/check-in", json=p)
    assert r2.status_code == 200
    response_data = r2.json()
    assert response_data["state"] == "insufficient_data"
    assert "2 check-in" in response_data["reflection"]
    assert "1 more" in response_data["reflection"]


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
    rate_limit_response = None
    for _ in range(10):
        r = client.post("/check-in", json=p)
        if r.status_code == 429:
            hit_429 = True
            rate_limit_response = r.json()
            break
        ok += 1

    assert hit_429, "Expected 429 after rapid calls"
    assert rate_limit_response is not None
    assert "retry_after_seconds" in rate_limit_response
    assert rate_limit_response["retry_after_seconds"] == 10


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


def test_help_endpoint():
    """Test the new help endpoint provides useful information."""
    response = client.get("/help")
    assert response.status_code == 200
    data = response.json()

    assert "api_info" in data
    assert "endpoints" in data
    assert "common_errors" in data
    assert "troubleshooting" in data

    # Check specific content
    assert data["api_info"]["title"] == "Single Compassionate Loop API"
    assert "HTTP_429" in data["common_errors"]
    assert "insufficient_data" in data["common_errors"]


def test_consent_not_found_provides_troubleshooting():
    """Test that missing consent records provide helpful error messages."""
    response = client.get("/consents/nonexistent_user")
    assert response.status_code == 200  # Returns 200 with error details
    data = response.json()

    assert data["detail"] == "not_found"
    assert "troubleshooting" in data
    assert "POST /consents" in data["troubleshooting"]


def test_empty_user_id_validation():
    """Test validation for empty user_id."""
    response = client.get("/consents/ ")  # Space only
    assert response.status_code == 400
    data = response.json()

    assert data["detail"] == "invalid_user_id"
    assert "troubleshooting" in data
