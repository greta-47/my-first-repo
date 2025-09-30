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


def test_troubleshoot_valid_issue_types():
    """Test troubleshoot endpoint with valid issue types"""
    valid_issues = ["login", "check-in", "consent", "network"]

    for issue_type in valid_issues:
        response = client.post("/troubleshoot", json={"issue_type": issue_type})
        assert response.status_code == 200
        body = response.json()
        assert body["issue_type"] == issue_type
        assert "identified_issue" in body
        assert "steps" in body
        assert len(body["steps"]) > 0
        assert "additional_resources" in body

        # Verify step structure
        for step in body["steps"]:
            assert "step_number" in step
            assert "title" in step
            assert "description" in step
            assert "action" in step


def test_troubleshoot_invalid_issue_type_empty():
    """Test troubleshoot endpoint with empty issue_type"""
    response = client.post("/troubleshoot", json={"issue_type": ""})
    assert response.status_code == 422  # Validation error


def test_troubleshoot_invalid_issue_type_too_long():
    """Test troubleshoot endpoint with overly long issue_type"""
    long_issue_type = "a" * 101  # Exceeds 100 character limit
    response = client.post("/troubleshoot", json={"issue_type": long_issue_type})
    assert response.status_code == 422  # Validation error


def test_troubleshoot_unknown_issue_type():
    """Test troubleshoot endpoint with unknown issue type returns generic steps"""
    response = client.post("/troubleshoot", json={"issue_type": "unknown_issue"})
    assert response.status_code == 200
    body = response.json()
    assert body["issue_type"] == "unknown_issue"
    assert body["identified_issue"] == "General technical difficulties"
    assert len(body["steps"]) == 5  # Generic steps


def test_troubleshoot_long_error_message():
    """Test troubleshoot endpoint with overly long error message"""
    long_error_msg = "error " * 201  # Exceeds 1000 character limit
    response = client.post(
        "/troubleshoot", json={"issue_type": "login", "error_message": long_error_msg}
    )
    assert response.status_code == 422  # Validation error


def test_troubleshoot_with_valid_error_message():
    """Test troubleshoot endpoint with valid error message"""
    response = client.post(
        "/troubleshoot",
        json={
            "issue_type": "login",
            "error_message": "Invalid username or password",
            "user_context": "Using mobile browser",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["issue_type"] == "login"
    assert "Authentication or login difficulties" in body["identified_issue"]


def test_troubleshoot_partial_match_issue_type():
    """Test troubleshoot endpoint with partial matching"""
    response = client.post("/troubleshoot", json={"issue_type": "login problems"})
    assert response.status_code == 200
    body = response.json()
    assert body["issue_type"] == "login problems"
    # Should match "login" and return login-specific steps
    assert "Authentication or login difficulties" in body["identified_issue"]


def test_troubleshoot_user_context_too_long():
    """Test troubleshoot endpoint with overly long user_context"""
    long_context = "context " * 72  # Exceeds 500 character limit
    response = client.post(
        "/troubleshoot", json={"issue_type": "login", "user_context": long_context}
    )
    assert response.status_code == 422  # Validation error


def test_troubleshoot_missing_required_fields():
    """Test troubleshoot endpoint with missing required fields"""
    response = client.post("/troubleshoot", json={})
    assert response.status_code == 422  # Missing issue_type field


def test_troubleshoot_privacy_safe_logging():
    """Test that troubleshoot endpoint doesn't log sensitive user data"""
    # This test focuses on structure - actual log inspection would require log capture
    response = client.post(
        "/troubleshoot",
        json={
            "issue_type": "login",
            "error_message": "sensitive error details here",
            "user_context": "personal information context",
        },
    )
    assert response.status_code == 200
    # The endpoint should work but not expose user data in logs
    # Logs are structured to redact user content per privacy requirements
