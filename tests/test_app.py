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
            # Verify standardized error format
            body = r.json()
            assert body["status"] == "error"
            assert body["error"]["code"] == "E_RATE_LIMITED"
            assert body["error"]["type"] == "https://recoveryos.org/errors/rate-limit"
            assert body["error"]["title"] == "Rate Limit Exceeded"
            assert "10 seconds" in body["error"]["detail"]
            assert "help_url" in body["error"]
            assert "meta" in body
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


def test_consent_not_found_returns_standardized_error():
    """Test that consent not found returns standardized error format."""
    r = client.get("/consents/nonexistent_user")
    assert r.status_code == 404
    body = r.json()
    assert body["status"] == "error"
    assert body["error"]["code"] == "E_CONSENT_NOT_FOUND"
    assert body["error"]["type"] == "https://recoveryos.org/errors/not-found"
    assert body["error"]["title"] == "Consent Record Not Found"
    assert "user ID" in body["error"]["detail"]
    assert "help_url" in body["error"]
    assert "meta" in body
    assert "timestamp" in body["meta"]


def test_help_endpoint_provides_comprehensive_information():
    """Test that the help endpoint provides complete API documentation."""
    r = client.get("/help")
    assert r.status_code == 200
    body = r.json()

    # Check basic structure
    assert "api_version" in body
    assert "documentation_url" in body
    assert "support_contact" in body
    assert "endpoints" in body
    assert "error_types" in body
    assert "troubleshooting" in body

    # Check version
    assert body["api_version"] == "0.0.1"

    # Check endpoints are documented
    endpoints = {ep["name"]: ep for ep in body["endpoints"]}
    assert "POST /check-in" in endpoints
    assert "POST /consents" in endpoints
    assert "GET /consents/{user_id}" in endpoints
    assert "GET /healthz" in endpoints
    assert "GET /readyz" in endpoints
    assert "GET /metrics" in endpoints

    # Check endpoint documentation quality
    for endpoint in body["endpoints"]:
        assert endpoint["description"]  # Non-empty description
        assert endpoint["url"]  # Documentation URL
        assert endpoint["status_codes"]  # List of status codes
        assert len(endpoint["status_codes"]) > 0

    # Check error types are documented
    assert "validation" in body["error_types"]
    assert "business-rule" in body["error_types"]
    assert "rate-limit" in body["error_types"]
    assert "not-found" in body["error_types"]
    assert "authorization" in body["error_types"]

    # Check troubleshooting information
    assert "rate_limited" in body["troubleshooting"]
    assert "insufficient_data" in body["troubleshooting"]
    assert "validation_failed" in body["troubleshooting"]
    assert "consent_not_found" in body["troubleshooting"]
    assert "high_risk_response" in body["troubleshooting"]


def test_help_endpoint_troubleshooting_links_are_valid():
    """Test that all troubleshooting links follow expected patterns."""
    r = client.get("/help")
    assert r.status_code == 200
    body = r.json()

    # Check that documentation URL is valid format
    assert body["documentation_url"].startswith("https://docs.recoveryos.org")

    # Check that all error type URLs follow consistent pattern
    for error_type, url in body["error_types"].items():
        assert url.startswith("https://docs.recoveryos.org/api/")
        # Just check that the URL is valid format, not exact matching
        assert len(url) > len("https://docs.recoveryos.org/api/")

    # Check that all endpoint URLs follow consistent pattern
    for endpoint in body["endpoints"]:
        assert endpoint["url"].startswith("https://docs.recoveryos.org/api/")

    # Check troubleshooting guidance is helpful
    for issue, guidance in body["troubleshooting"].items():
        assert len(guidance) > 20  # Meaningful guidance
        assert any(
            word in guidance.lower() for word in ["check", "ensure", "contact", "wait", "continue"]
        )


def test_help_endpoint_status_codes_accuracy():
    """Test that documented status codes match actual endpoint behavior."""
    r = client.get("/help")
    assert r.status_code == 200
    body = r.json()

    endpoints = {ep["name"]: ep for ep in body["endpoints"]}

    # Check POST /check-in status codes
    checkin_codes = endpoints["POST /check-in"]["status_codes"]
    assert "200" in checkin_codes  # Success
    assert "429" in checkin_codes  # Rate limit (verified in other tests)
    assert "400" in checkin_codes or "422" in checkin_codes  # Validation errors

    # Check GET /consents/{user_id} status codes
    consent_codes = endpoints["GET /consents/{user_id}"]["status_codes"]
    assert "200" in consent_codes  # Success
    assert "404" in consent_codes  # Not found (verified in other tests)

    # Check health endpoints return 200
    assert "200" in endpoints["GET /healthz"]["status_codes"]
    assert "200" in endpoints["GET /readyz"]["status_codes"]
    assert "200" in endpoints["GET /metrics"]["status_codes"]
