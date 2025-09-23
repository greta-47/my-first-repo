from fastapi.testclient import TestClient

from app.main import RATE_BUCKETS, app

client = TestClient(app)


def setup_function():
    RATE_BUCKETS.clear()


def test_checkin_insufficient_data():
    payload = {
        "user_id": "test_user_1",
        "checkins_count": 2,
        "days_since_last_checkin": 1,
        "craving": 5.0,
        "mood": 3,
    }

    response = client.post("/check-in", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["state"] == "insufficient_data"
    assert data["score"] is None
    assert data["band"] is None
    assert len(data["reflection"]) > 0
    assert len(data["crisis_footer"]) > 0


def test_checkin_high_risk_band():
    payload = {
        "user_id": "test_user_2",
        "checkins_count": 5,
        "days_since_last_checkin": 5,
        "craving": 10.0,
        "mood": 1,
        "previous_mood": 4,
        "sleep_quality": "poor",
        "sleep_hours": 3.0,
        "isolation_level": "often",
    }

    response = client.post("/check-in", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["band"] == "high"
    assert data["score"] is not None
    assert data["score"] >= 75
    assert len(data["reflection"]) > 0
    assert len(data["crisis_footer"]) > 0


def test_checkin_rate_limiting():
    payload = {
        "user_id": "test_user_3",
        "checkins_count": 5,
        "days_since_last_checkin": 1,
        "craving": 3.0,
        "mood": 4,
    }

    for i in range(60):
        response = client.post("/check-in", json=payload)
        if i < 59:
            assert response.status_code == 200

    response = client.post("/check-in", json=payload)
    assert response.status_code == 429
    assert "Too Many Requests" in response.json()["detail"]


def test_checkin_low_risk_band():
    payload = {
        "user_id": "test_user_4",
        "checkins_count": 10,
        "days_since_last_checkin": 0,
        "craving": 1.0,
        "mood": 5,
        "previous_mood": 4,
        "sleep_quality": "good",
        "sleep_hours": 8.0,
        "isolation_level": "none",
    }

    response = client.post("/check-in", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["band"] == "low"
    assert data["score"] is not None
    assert data["score"] <= 29
    assert len(data["reflection"]) > 0


def test_checkin_moderate_risk_band():
    payload = {
        "user_id": "test_user_5",
        "checkins_count": 8,
        "days_since_last_checkin": 2,
        "craving": 5.0,
        "mood": 3,
        "sleep_quality": "average",
        "isolation_level": "sometimes",
    }

    response = client.post("/check-in", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["band"] == "moderate"
    assert data["score"] is not None
    assert 30 <= data["score"] <= 54
    assert "Some stress signals" in data["reflection"]
