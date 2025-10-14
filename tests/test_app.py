import os

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["app_version"] = "0.0.1"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import metadata

test_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(autouse=True)
def setup_database():
    """Create tables before each test and drop them after."""
    metadata.create_all(bind=test_engine)
    yield
    metadata.drop_all(bind=test_engine)


@pytest.fixture
def client():
    """Create a test client with clean database for each test."""
    import app.database
    import app.main
    from app.database import get_db
    from app.main import app as fastapi_app

    original_engine_ref = app.database.engine
    app.database.engine = test_engine
    app.main.engine = test_engine

    def override_get_db():
        db = TestSessionLocal()
        try:
            yield db
        finally:
            db.close()

    fastapi_app.dependency_overrides[get_db] = override_get_db

    with TestClient(fastapi_app) as test_client:
        yield test_client

    fastapi_app.dependency_overrides.clear()
    app.database.engine = original_engine_ref
    app.main.engine = original_engine_ref


def test_insufficient_data_before_three_checkins(client):
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


def test_high_risk_payload_yields_high_band_and_crisis_footer(client):
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


def test_rate_limit_returns_429_after_rapid_calls(client):
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


def test_consents_roundtrip(client):
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


# ---- Troubleshoot tests (keep) ----
def test_troubleshoot_valid_issue_types(client):
    valid_issues = ["login", "check-in", "consent", "network"]
    for issue_type in valid_issues:
        response = client.post("/troubleshoot", json={"issue_type": issue_type})
        assert response.status_code == 200
        body = response.json()
        assert body["issue_type"] == issue_type
        assert "identified_issue" in body
        assert "steps" in body and len(body["steps"]) > 0
        assert "additional_resources" in body
        for step in body["steps"]:
            assert (
                "step_number" in step
                and "title" in step
                and "description" in step
                and "action" in step
            )


def test_troubleshoot_invalid_issue_type_empty(client):
    response = client.post("/troubleshoot", json={"issue_type": ""})
    assert response.status_code == 422


def test_troubleshoot_invalid_issue_type_too_long(client):
    long_issue_type = "a" * 101
    response = client.post("/troubleshoot", json={"issue_type": long_issue_type})
    assert response.status_code == 422


def test_troubleshoot_unknown_issue_type(client):
    response = client.post("/troubleshoot", json={"issue_type": "unknown_issue"})
    assert response.status_code == 200
    body = response.json()
    assert body["issue_type"] == "unknown_issue"
    assert body["identified_issue"] == "General technical difficulties"
    assert len(body["steps"]) == 5


def test_troubleshoot_long_error_message(client):
    long_error_msg = "error " * 201
    response = client.post(
        "/troubleshoot", json={"issue_type": "login", "error_message": long_error_msg}
    )
    assert response.status_code == 422


def test_troubleshoot_with_valid_error_message(client):
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


def test_troubleshoot_partial_match_issue_type(client):
    response = client.post("/troubleshoot", json={"issue_type": "login problems"})
    assert response.status_code == 200
    body = response.json()
    assert body["issue_type"] == "login problems"
    assert "Authentication or login difficulties" in body["identified_issue"]


def test_troubleshoot_user_context_too_long(client):
    long_context = "context " * 72
    response = client.post(
        "/troubleshoot", json={"issue_type": "login", "user_context": long_context}
    )
    assert response.status_code == 422


def test_troubleshoot_missing_required_fields(client):
    response = client.post("/troubleshoot", json={})
    assert response.status_code == 422


def test_troubleshoot_privacy_safe_logging(client):
    response = client.post(
        "/troubleshoot",
        json={
            "issue_type": "login",
            "error_message": "sensitive error details here",
            "user_context": "personal information context",
        },
    )
    assert response.status_code == 200


# ---- Help/Error tests (keep) ----
def test_consent_not_found_returns_standardized_error(client):
    r = client.get("/consents/nonexistent_user")
    assert r.status_code == 404
    body = r.json()
    assert body["status"] == "error"
    assert body["error"]["code"] == "E_CONSENT_NOT_FOUND"
    assert body["error"]["type"] == "https://recoveryos.org/errors/not-found"
    assert body["error"]["title"] == "Consent Record Not Found"
    assert "user ID" in body["error"]["detail"]
    assert "help_url" in body
    assert "meta" in body
    assert "timestamp" in body["meta"]


def test_help_endpoint_provides_comprehensive_information(client):
    r = client.get("/help")
    assert r.status_code == 200
    body = r.json()
    assert "api_version" in body and body["api_version"] == "0.0.1"
    assert "documentation_url" in body and "support_contact" in body
    assert "endpoints" in body and "error_types" in body and "troubleshooting" in body
    endpoints = {ep["name"]: ep for ep in body["endpoints"]}
    for name in [
        "POST /check-in",
        "POST /consents",
        "GET /consents/{user_id}",
        "GET /healthz",
        "GET /readyz",
        "GET /metrics",
    ]:
        assert name in endpoints
    for endpoint in body["endpoints"]:
        assert endpoint["description"]
        assert endpoint["url"]
        assert endpoint["status_codes"] and len(endpoint["status_codes"]) > 0
    for key in ["validation", "business-rule", "rate-limit", "not-found", "authorization"]:
        assert key in body["error_types"]
    for key in [
        "rate_limited",
        "insufficient_data",
        "validation_failed",
        "consent_not_found",
        "high_risk_response",
    ]:
        assert key in body["troubleshooting"]


def test_help_endpoint_troubleshooting_links_are_valid(client):
    r = client.get("/help")
    assert r.status_code == 200
    body = r.json()
    assert body["documentation_url"].startswith("https://docs.recoveryos.org")
    for _, url in body["error_types"].items():
        assert url.startswith("https://docs.recoveryos.org/api/")
        assert len(url) > len("https://docs.recoveryos.org/api/")
    for endpoint in body["endpoints"]:
        assert endpoint["url"].startswith("https://docs.recoveryos.org/api/")
    for _, guidance in body["troubleshooting"].items():
        assert len(guidance) > 20
        assert any(
            w in guidance.lower() for w in ["check", "ensure", "contact", "wait", "continue"]
        )


def test_help_endpoint_status_codes_accuracy(client):
    r = client.get("/help")
    assert r.status_code == 200
    body = r.json()
    endpoints = {ep["name"]: ep for ep in body["endpoints"]}
    checkin_codes = endpoints["POST /check-in"]["status_codes"]
    assert (
        "200" in checkin_codes
        and ("400" in checkin_codes or "422" in checkin_codes)
        and "429" in checkin_codes
    )
    consent_codes = endpoints["GET /consents/{user_id}"]["status_codes"]
    assert "200" in consent_codes and "404" in consent_codes
    assert "200" in endpoints["GET /healthz"]["status_codes"]
    assert "200" in endpoints["GET /readyz"]["status_codes"]
    assert "200" in endpoints["GET /metrics"]["status_codes"]
