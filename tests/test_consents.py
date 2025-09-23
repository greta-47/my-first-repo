from fastapi.testclient import TestClient

from app.main import CONSENTS, RATE_BUCKETS, app

client = TestClient(app)


def setup_function():
    CONSENTS.clear()
    RATE_BUCKETS.clear()


def test_consents_post_get_roundtrip():
    user_id = "test_user_consent_1"

    get_response = client.get(f"/consents?user_id={user_id}")
    assert get_response.status_code == 200
    initial_data = get_response.json()
    assert initial_data["user_id"] == user_id
    assert initial_data["family_sharing"] is False
    assert initial_data["scope"] == "weekly_summary"
    assert initial_data["timestamp"] is None

    post_payload = {"user_id": user_id, "family_sharing": True, "scope": "weekly_summary"}

    post_response = client.post("/consents", json=post_payload)
    assert post_response.status_code == 200
    post_data = post_response.json()
    assert post_data["user_id"] == user_id
    assert post_data["family_sharing"] is True
    assert post_data["scope"] == "weekly_summary"
    assert post_data["timestamp"] is not None

    get_response_after = client.get(f"/consents?user_id={user_id}")
    assert get_response_after.status_code == 200
    final_data = get_response_after.json()
    assert final_data["user_id"] == user_id
    assert final_data["family_sharing"] is True
    assert final_data["scope"] == "weekly_summary"
    assert final_data["timestamp"] == post_data["timestamp"]


def test_consents_revoke():
    user_id = "test_user_consent_2"

    enable_payload = {"user_id": user_id, "family_sharing": True, "scope": "weekly_summary"}

    client.post("/consents", json=enable_payload)

    revoke_payload = {"user_id": user_id, "family_sharing": False, "scope": "weekly_summary"}

    revoke_response = client.post("/consents", json=revoke_payload)
    assert revoke_response.status_code == 200
    revoke_data = revoke_response.json()
    assert revoke_data["family_sharing"] is False

    get_response = client.get(f"/consents?user_id={user_id}")
    assert get_response.status_code == 200
    final_data = get_response.json()
    assert final_data["family_sharing"] is False


def test_consents_rate_limiting():
    payload = {"user_id": "test_user_rate_limit", "family_sharing": True, "scope": "weekly_summary"}

    for i in range(30):
        response = client.post("/consents", json=payload)
        if i < 29:
            assert response.status_code == 200

    response = client.post("/consents", json=payload)
    assert response.status_code == 429
    assert "Too Many Requests" in response.json()["detail"]


def test_consents_custom_scope():
    user_id = "test_user_consent_3"

    payload = {"user_id": user_id, "family_sharing": True, "scope": "daily_summary"}

    response = client.post("/consents", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["scope"] == "daily_summary"

    get_response = client.get(f"/consents?user_id={user_id}")
    assert get_response.status_code == 200
    get_data = get_response.json()
    assert get_data["scope"] == "daily_summary"
