import json


def _file(client, reason="Please review this decision", ip="10.0.1.1"):
    return client.post(
        "/api/public/redress-request",
        data=json.dumps({"reason": reason}),
        content_type="application/json",
        headers={"X-Forwarded-For": ip},
    ).get_json()["request_ref"]


def test_internal_endpoints_require_key_or_admin(client):
    resp = client.get("/api/internal/redress-requests")
    assert resp.status_code == 403


def test_internal_list_with_valid_key(client, monkeypatch):
    monkeypatch.setenv("CREED_INTERNAL_KEY", "testkey")
    _file(client)

    resp = client.get("/api/internal/redress-requests", headers={"X-Internal-Key": "testkey"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert data["count"] == 1
    assert data["requests"][0]["status"] == "pending"


def test_internal_list_rejects_wrong_key(client, monkeypatch):
    monkeypatch.setenv("CREED_INTERNAL_KEY", "testkey")
    resp = client.get("/api/internal/redress-requests", headers={"X-Internal-Key": "wrong"})
    assert resp.status_code == 403


def test_internal_list_status_filter(client, monkeypatch):
    monkeypatch.setenv("CREED_INTERNAL_KEY", "testkey")
    ref = _file(client)
    client.post(
        f"/api/internal/redress-requests/{ref}/resolve",
        data=json.dumps({"status": "resolved", "resolution_notes": "Reviewed, no error found."}),
        content_type="application/json",
        headers={"X-Internal-Key": "testkey"},
    )

    pending = client.get(
        "/api/internal/redress-requests?status=pending", headers={"X-Internal-Key": "testkey"}
    ).get_json()
    assert pending["count"] == 0

    resolved = client.get(
        "/api/internal/redress-requests?status=resolved", headers={"X-Internal-Key": "testkey"}
    ).get_json()
    assert resolved["count"] == 1
    assert resolved["requests"][0]["resolution_notes"] == "Reviewed, no error found."


def test_internal_resolve_rejects_bad_status(client, monkeypatch):
    monkeypatch.setenv("CREED_INTERNAL_KEY", "testkey")
    ref = _file(client)
    resp = client.post(
        f"/api/internal/redress-requests/{ref}/resolve",
        data=json.dumps({"status": "not-a-real-status"}),
        content_type="application/json",
        headers={"X-Internal-Key": "testkey"},
    )
    assert resp.status_code == 400


def test_internal_resolve_unknown_ref_is_404(client, monkeypatch):
    monkeypatch.setenv("CREED_INTERNAL_KEY", "testkey")
    resp = client.post(
        "/api/internal/redress-requests/RR-NOPE0000/resolve",
        data=json.dumps({"status": "denied"}),
        content_type="application/json",
        headers={"X-Internal-Key": "testkey"},
    )
    assert resp.status_code == 404


def test_internal_resolve_reflected_in_public_stats(client, monkeypatch):
    monkeypatch.setenv("CREED_INTERNAL_KEY", "testkey")
    ref = _file(client)
    client.post(
        f"/api/internal/redress-requests/{ref}/resolve",
        data=json.dumps({"status": "denied", "resolution_notes": "Decision was correct."}),
        content_type="application/json",
        headers={"X-Internal-Key": "testkey"},
    )
    stats = client.get("/api/public/accountability").get_json()
    assert stats["by_status"]["denied"] == 1
    assert stats["by_status"]["pending"] == 0
