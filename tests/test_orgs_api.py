"""Multi-tenant P1.2 tests (task #3269). Run in SQLite mode (no PG), so they
cover the degradation contracts + the pure guard logic in tenant_auth."""

from kytran_creed.tenant_auth import (
    KEY_PREFIX,
    _EMAIL_RE,
    _PHONE_RE,
    generate_api_key,
    ingest_guard,
)


def test_generate_api_key_shape():
    raw, key_hash = generate_api_key()
    assert raw.startswith(KEY_PREFIX)
    assert len(key_hash) == 64  # sha256 hex


def test_pii_regexes():
    assert _EMAIL_RE.search("contact admin@example.com now")
    assert _PHONE_RE.search("call +1 514 555 0199 today")
    assert _PHONE_RE.search("call 514-555-0199 today")
    # systems-speak must NOT trip the firewall
    assert not _EMAIL_RE.search("agent V.E.R.I.F.Y. dispatched 353061 events")
    assert not _PHONE_RE.search("hub at 192.168.1.200 mesh 100.64.0.4 v2.10.3")


def test_ingest_guard_metadata_cap(app):
    with app.test_request_context():
        err = ingest_guard("clean description", "x" * 5000)
        assert err is not None and err[1] == 400


def test_ingest_guard_clean(app):
    with app.test_request_context():
        assert ingest_guard("welfare rest cycle completed", '{"agent": "K.I.N."}') is None


def test_orgs_directory_requires_pg(client):
    r = client.get("/api/v1/orgs")
    assert r.status_code == 503


def test_tenant_badge_requires_pg(client):
    r = client.get("/api/v1/badge/some-org/overall")
    assert r.status_code == 503


def test_post_event_with_invalid_bearer_rejected(client):
    r = client.post(
        "/api/v1/events",
        json={
            "event_type": "test",
            "source_platform": "pytest",
            "agent_id": "t1",
            "category": "safety",
            "severity": "info",
            "description": "test event",
        },
        headers={"Authorization": "Bearer not_a_creed_key"},
    )
    assert r.status_code == 401


def test_keyless_rejected_when_keys_required(client, monkeypatch):
    """P2.1 kill-switch: REQUIRE_INGEST_KEYS=true → keyless ingest 401."""
    monkeypatch.setenv("REQUIRE_INGEST_KEYS", "true")
    r = client.post(
        "/api/v1/events",
        json={
            "event_type": "test",
            "source_platform": "pytest",
            "agent_id": "t1",
            "category": "safety",
            "severity": "info",
            "description": "should be rejected",
        },
    )
    assert r.status_code == 401


def test_get_scored_page_renders(client):
    r = client.get("/get-scored")
    assert r.status_code == 200
    assert b"Apply for scoring" in r.data


def test_onboarding_apply_requires_pg(client):
    r = client.post(
        "/api/v1/onboarding/apply",
        json={
            "slug": "test-org",
            "name": "Test Org",
            "website": "https://example.com",
            "contact_email": "a@example.com",
            "ai_description": "we run a fleet of helpful AI agents",
        },
    )
    assert r.status_code == 503


def test_org_profile_template_renders(app):
    """org_profile.html must render against the real base.html context.
    Regression: passing the tenant as `t=` shadowed the i18n t() helper from
    base.html ('dict' object is not callable → 500 on every /org/<slug>)."""
    from flask import render_template

    tenant = {
        "slug": "test-org",
        "name": "Test Org",
        "website": "https://example.com",
        "country": "Canada",
        "member_since": "2026-06-09T00:00:00",
    }
    with app.test_request_context("/org/test-org"):
        html = render_template(
            "org_profile.html",
            org=tenant,
            scores={"overall": 95.0, "grade": "A", "event_count": 120, "by_category": {}},
            pillars=[("Safety", {"score": 95.0, "grade": "A", "color": "#10b981"})],
            freshness={
                "provisional": False,
                "events_30d": 120,
                "total_events": 120,
                "categories_active": 3,
                "span_days": 15.0,
                "last_event_at": "2026-06-09T00:00:00",
            },
            gate={"events": 100, "categories": 3, "days": 14},
            color="#10b981",
            tier_label="SELF-REPORTED",
            last_reported="just now",
            incidents_disclosed=0,
        )
    assert "Test Org" in html
    assert "/org/test-org" in html


def test_event_json_schema_matches_validator(client):
    """/api/v1/schema enums must equal the constants validate() enforces —
    the published standard can never drift from the actual validator."""
    from kytran_creed.models import REQUIRED_EVENT_FIELDS, VALID_CATEGORIES, VALID_SEVERITIES

    r = client.get("/api/v1/schema")
    assert r.status_code == 200
    schema = r.get_json()
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert set(schema["required"]) == REQUIRED_EVENT_FIELDS
    assert set(schema["properties"]["category"]["enum"]) == VALID_CATEGORIES
    assert set(schema["properties"]["severity"]["enum"]) == VALID_SEVERITIES
    assert "schema_version" in schema["properties"]
    assert r.headers["Access-Control-Allow-Origin"] == "*"


def test_standard_page_renders(client):
    r = client.get("/standard")
    assert r.status_code == 200
    assert b"Event Schema" in r.data
    assert b"/api/v1/schema" in r.data
    # every pillar + severity from the validator must appear on the page
    from kytran_creed.models import VALID_CATEGORIES, VALID_SEVERITIES

    for name in VALID_CATEGORIES | VALID_SEVERITIES:
        assert name.encode() in r.data


def test_post_event_with_schema_version_tolerated(client):
    """Emitters may pin schema_version — ingest must accept and ignore it."""
    r = client.post(
        "/api/v1/events",
        json={
            "event_type": "test",
            "source_platform": "pytest",
            "agent_id": "t1",
            "category": "safety",
            "severity": "info",
            "description": "event pinned to schema v1",
            "schema_version": "1",
        },
    )
    assert r.status_code == 201


def test_post_event_keyless_still_works(client):
    """The institute's legacy keyless feed must keep working (P2 retires it)."""
    r = client.post(
        "/api/v1/events",
        json={
            "event_type": "test",
            "source_platform": "pytest",
            "agent_id": "t1",
            "category": "safety",
            "severity": "info",
            "description": "keyless institute event",
        },
    )
    assert r.status_code == 201
    assert r.get_json()["success"] is True
