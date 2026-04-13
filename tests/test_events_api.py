import json


def test_post_event_returns_201(client):
    event = {
        "event_type": "agent_action",
        "source_platform": "archie",
        "agent_id": "agent-131",
        "agent_name": "Beacon-A",
        "category": "transparency",
        "severity": "info",
        "description": "Agent completed task with full audit trail",
    }
    resp = client.post("/api/v1/events", json=event)
    assert resp.status_code == 201
    data = resp.get_json()
    assert data["success"] is True
    assert "event_id" in data


def test_post_event_missing_fields_returns_400(client):
    resp = client.post("/api/v1/events", json={"event_type": "agent_action"})
    assert resp.status_code == 400


def test_get_events_returns_list(client):
    event = {
        "event_type": "agent_action",
        "source_platform": "archie",
        "agent_id": "agent-1",
        "agent_name": "Test",
        "category": "safety",
        "severity": "info",
        "description": "Test event",
    }
    client.post("/api/v1/events", json=event)
    resp = client.get("/api/v1/events")
    assert resp.status_code == 200
    data = resp.get_json()
    assert isinstance(data["events"], list)
    assert len(data["events"]) >= 1


def test_get_audit_trail(client):
    resp = client.get("/api/v1/audit")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "entries" in data
