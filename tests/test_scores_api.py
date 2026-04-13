def test_get_scores(client):
    for sev in ["info", "info", "warning"]:
        client.post(
            "/api/v1/events",
            json={
                "event_type": "agent_action",
                "source_platform": "test",
                "agent_id": "a1",
                "agent_name": "Test",
                "category": "safety",
                "severity": sev,
                "description": "test",
            },
        )
    resp = client.get("/api/v1/scores")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "overall" in data
    assert "grade" in data
    assert "by_category" in data
