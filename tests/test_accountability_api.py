import json


def test_accountability_stats_empty(client):
    resp = client.get("/api/public/accountability")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["total"] == 0
    assert data["by_status"] == {"pending": 0, "under_review": 0, "resolved": 0, "denied": 0}
    assert data["avg_resolution_days"] is None
    assert data["sla_business_days"] == 5
    assert data["resolution_is_human"] is True
    assert resp.headers["Access-Control-Allow-Origin"] == "*"


def test_redress_request_requires_reason(client):
    resp = client.post(
        "/api/public/redress-request",
        data=json.dumps({"reason": "  "}),
        content_type="application/json",
        headers={"X-Forwarded-For": "10.0.0.1"},
    )
    assert resp.status_code == 400
    assert "contest" in resp.get_json()["error"].lower()


def test_redress_request_rejects_bad_email(client):
    resp = client.post(
        "/api/public/redress-request",
        data=json.dumps({"reason": "It flagged my post unfairly.", "email": "not-an-email"}),
        content_type="application/json",
        headers={"X-Forwarded-For": "10.0.0.2"},
    )
    assert resp.status_code == 400
    assert "email" in resp.get_json()["error"].lower()


def test_redress_request_success_then_reflected_in_stats(client):
    resp = client.post(
        "/api/public/redress-request",
        data=json.dumps(
            {
                "reason": "It flagged my post unfairly.",
                "ai_decision_ref": "BIAS-123",
                "desired_outcome": "Re-review",
                "email": "person@example.com",
            }
        ),
        content_type="application/json",
        headers={"X-Forwarded-For": "10.0.0.3"},
    )
    assert resp.status_code == 201
    body = resp.get_json()
    assert body["request_ref"].startswith("RR-")
    assert body["sla_due_at"].endswith("Z")

    stats = client.get("/api/public/accountability").get_json()
    assert stats["total"] == 1
    assert stats["by_status"]["pending"] == 1


def test_redress_request_rate_limited_after_five(client):
    for _ in range(5):
        r = client.post(
            "/api/public/redress-request",
            data=json.dumps({"reason": "spam test"}),
            content_type="application/json",
            headers={"X-Forwarded-For": "10.0.0.4"},
        )
        assert r.status_code == 201
    sixth = client.post(
        "/api/public/redress-request",
        data=json.dumps({"reason": "spam test"}),
        content_type="application/json",
        headers={"X-Forwarded-For": "10.0.0.4"},
    )
    assert sixth.status_code == 429
