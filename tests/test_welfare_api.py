"""Phase 2 — AI-workforce welfare public metric (WP-002 §8).

Verifies the welfare scorer + public endpoints, AND that the existing 6-pillar
ethics score is untouched (welfare never leaks into the pillars).
"""

from kytran_creed.services.scoring_engine import CATEGORIES, calculate_scores
from kytran_creed.services.welfare_engine import DIMENSIONS, calculate_welfare


# ── Scorer unit tests ────────────────────────────────────────────────────────

def test_welfare_empty_is_provisional_not_error():
    r = calculate_welfare([], span_days=0.0)
    assert r["provisional"] is True
    assert r["grade"] == "PROVISIONAL"
    assert r["overall"] is None
    assert set(r["by_dimension"].keys()) == set(DIMENSIONS)
    assert r["event_count"] == 0
    assert r["break_honor_rate"] is None
    assert r["agents_monitored"] == 0


def test_welfare_scores_by_dimension_and_severity():
    events = [
        {"severity": "info", "event_type": "welfare_hours", "agent_id": "a1",
         "metadata": {"dimension": "hours"}},
        {"severity": "critical", "event_type": "welfare_tokens", "agent_id": "a2",
         "metadata": {"dimension": "tokens"}},
        {"severity": "info", "event_type": "welfare_actions", "agent_id": "a1",
         "metadata": {"dimension": "actions"}},
        {"severity": "warning", "event_type": "welfare_stress", "agent_id": "a3",
         "metadata": {"dimension": "stress"}},
    ]
    r = calculate_welfare(events, span_days=20.0)
    assert r["by_dimension"]["hours"]["score"] == 100.0
    assert r["by_dimension"]["tokens"]["score"] == 0.0  # critical = max weight
    assert r["agents_monitored"] == 3
    assert r["event_count"] == 4
    # 4 events < gate(100) → still provisional, but scores are computed + visible
    assert r["provisional"] is True
    assert r["overall_raw"] is not None


def test_welfare_break_honor_rate():
    events = [
        {"severity": "info", "event_type": "welfare_break_honored", "agent_id": "a1"},
        {"severity": "info", "event_type": "welfare_break_honored", "agent_id": "a2"},
        {"severity": "violation", "event_type": "welfare_break_violated", "agent_id": "a3"},
    ]
    r = calculate_welfare(events, span_days=1.0)
    assert r["break_honor_rate"] == round(2 / 3, 3)


def test_welfare_dimension_from_event_type_without_metadata():
    events = [{"severity": "info", "event_type": "welfare_tokens_over", "agent_id": "a1"}]
    r = calculate_welfare(events, span_days=0.0)
    assert r["by_dimension"]["tokens"]["events"] == 1


# ── Endpoint tests ───────────────────────────────────────────────────────────

def test_get_welfare_endpoint_clean_when_no_data(client):
    resp = client.get("/api/v1/welfare")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["provisional"] is True
    assert "by_dimension" in data
    assert "generated_at" in data
    assert data["cache_seconds"] == 60
    assert resp.headers["Access-Control-Allow-Origin"] == "*"


def test_get_welfare_after_ingest(client):
    for sev in ["info", "info", "warning"]:
        r = client.post(
            "/api/v1/events",
            json={
                "event_type": "welfare_hours",
                "source_platform": "archie-hub",
                "agent_id": "agent-131",
                "agent_name": "Beacon",
                "category": "welfare",
                "severity": sev,
                "description": "agent on-duty hours within rest cadence",
                "metadata": {"dimension": "hours"},
            },
        )
        assert r.status_code == 201
    resp = client.get("/api/v1/welfare")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["event_count"] == 3
    assert data["by_dimension"]["hours"]["events"] == 3


def test_welfare_methodology_endpoint(client):
    resp = client.get("/api/v1/welfare/methodology")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["standard"] == "C.R.E.E.D. WP-002"
    assert [d["key"] for d in data["dimensions"]] == DIMENSIONS
    assert "provisional_gate" in data
    assert "token_budgets" in data
    assert "separation_guarantee" in data


def test_welfare_badge_svg(client):
    resp = client.get("/api/v1/badge/welfare")
    assert resp.status_code == 200
    assert resp.content_type.startswith("image/svg+xml")
    assert b"<svg" in resp.data
    assert b"Welfare" in resp.data
    # No welfare data yet → provisional-gray badge.
    assert b"PROVISIONAL" in resp.data


# ── Separation guarantee: welfare must NOT touch the ethics pillars ───────────

def test_welfare_category_excluded_from_ethics_pillars():
    assert "welfare" not in CATEGORIES
    # A pile of critical welfare events must NOT move the ethics overall.
    ethics_events = [{"category": "welfare", "severity": "critical"} for _ in range(50)]
    scores = calculate_scores(ethics_events)
    # No ethics category recorded any events → overall stays 100 / A+.
    assert scores["overall"] == 100.0
    for cat in CATEGORIES:
        assert scores["by_category"][cat]["events"] == 0


def test_welfare_event_accepted_at_ingest_but_not_in_ethics_scores(client):
    r = client.post(
        "/api/v1/events",
        json={
            "event_type": "welfare_tokens",
            "source_platform": "archie-hub",
            "agent_id": "agent-200",
            "agent_name": "Forge",
            "category": "welfare",
            "severity": "critical",
            "description": "agent exceeded token budget",
            "metadata": {"dimension": "tokens"},
        },
    )
    assert r.status_code == 201
    # Ethics scores must be unaffected by the welfare event.
    scores = client.get("/api/v1/scores").get_json()
    for cat in CATEGORIES:
        assert scores["by_category"][cat]["events"] == 0


def test_welfare_ingest_does_not_inflate_ethics_event_count(client):
    """Phase 3 nit: welfare events must NOT inflate the public ethics event_count.

    _get_recent_events now excludes category='welfare', so /api/v1/scores
    event_count counts ONLY ethics events. Ingest a mix and assert the ethics
    tally reflects the ethics events only, and the overall + 6 pillars are
    unchanged by the welfare ingest.
    """
    def post(category, event_type, severity, **kw):
        body = {
            "event_type": event_type,
            "source_platform": "archie-hub",
            "agent_id": kw.get("agent_id", "agent-1"),
            "agent_name": "Forge",
            "category": category,
            "severity": severity,
            "description": "test event",
            "metadata": kw.get("metadata", {}),
        }
        resp = client.post("/api/v1/events", json=body)
        assert resp.status_code == 201

    # Baseline: ethics-only feed.
    post("transparency", "model_disclosure", "info")
    post("safety", "guardrail_pass", "info")
    base = client.get("/api/v1/scores").get_json()
    assert base["event_count"] == 2

    # Ingest a pile of welfare events (would inflate event_count if not filtered).
    for _ in range(10):
        post("welfare", "welfare_tokens", "critical", metadata={"dimension": "tokens"})

    after = client.get("/api/v1/scores").get_json()
    # event_count counts ONLY the 2 ethics events — welfare is excluded.
    assert after["event_count"] == 2
    # Overall + every pillar identical to the pre-welfare baseline.
    assert after["overall"] == base["overall"]
    for cat in CATEGORIES:
        assert after["by_category"][cat]["events"] == base["by_category"][cat]["events"]
        assert after["by_category"][cat]["score"] == base["by_category"][cat]["score"]

    # And the welfare endpoint DOES see those welfare events (its own fetch).
    welfare = client.get("/api/v1/welfare").get_json()
    assert welfare["event_count"] == 10
