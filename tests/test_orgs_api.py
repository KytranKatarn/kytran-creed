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
