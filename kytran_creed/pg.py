import os
import logging
import psycopg2
import psycopg2.extras
from kytran_creed.config import Config

logger = logging.getLogger(__name__)
_pg_available = False

SCHEMA = """
CREATE TABLE IF NOT EXISTS governance_events (
    id SERIAL PRIMARY KEY,
    event_type VARCHAR(50) NOT NULL,
    source_platform VARCHAR(100) NOT NULL,
    agent_id VARCHAR(100) NOT NULL,
    agent_name VARCHAR(200),
    category VARCHAR(50) NOT NULL,
    severity VARCHAR(20) NOT NULL,
    description TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_events_category ON governance_events(category);
CREATE INDEX IF NOT EXISTS idx_events_severity ON governance_events(severity);
CREATE INDEX IF NOT EXISTS idx_events_platform ON governance_events(source_platform);
CREATE INDEX IF NOT EXISTS idx_events_created ON governance_events(created_at);

CREATE TABLE IF NOT EXISTS incident_log (
    id SERIAL PRIMARY KEY,
    incident_ref VARCHAR(40) UNIQUE NOT NULL,
    severity VARCHAR(20) NOT NULL,
    title VARCHAR(300) NOT NULL,
    description TEXT,
    affected_agents TEXT,
    root_cause TEXT,
    resolution TEXT,
    status VARCHAR(20) NOT NULL DEFAULT 'investigating',
    lessons_learned TEXT,
    disclosed BOOLEAN NOT NULL DEFAULT FALSE,
    disclosed_at TIMESTAMP,
    occurred_at TIMESTAMP DEFAULT NOW(),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_incident_disclosed ON incident_log(disclosed, disclosed_at);
CREATE INDEX IF NOT EXISTS idx_incident_severity ON incident_log(severity);

CREATE TABLE IF NOT EXISTS aia_assessments (
    id SERIAL PRIMARY KEY,
    name VARCHAR(300) NOT NULL,
    purpose TEXT NOT NULL,
    affected_parties TEXT NOT NULL,
    decision_type VARCHAR(50) NOT NULL DEFAULT 'advisory',
    human_oversight TEXT NOT NULL,
    risk_tier VARCHAR(20) NOT NULL DEFAULT 'limited',
    data_sources TEXT,
    known_limitations TEXT,
    mitigation_measures TEXT,
    review_cadence VARCHAR(100),
    answers_json JSONB DEFAULT '{}',
    status VARCHAR(20) NOT NULL DEFAULT 'draft',
    created_by VARCHAR(100),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    tenant_id UUID REFERENCES tenants(id)
);
CREATE INDEX IF NOT EXISTS idx_aia_tenant ON aia_assessments(tenant_id);
CREATE INDEX IF NOT EXISTS idx_aia_status ON aia_assessments(status);
"""

INSTITUTE_SLUG = "creed-institute"

# Multi-tenant migration (task #3269 P1.1, ADR-004). Idempotent — runs on every
# startup after SCHEMA. The Institute itself is tenant #1 on the same pipeline.
# tenant_id gets a column DEFAULT of the institute tenant's UUID so existing
# single-tenant ingest paths (which don't pass tenant_id) keep working until
# P1.2 makes API-key-scoped inserts explicit.
TENANT_MIGRATION = """
CREATE TABLE IF NOT EXISTS tenants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug VARCHAR(80) UNIQUE NOT NULL,
    name VARCHAR(200) NOT NULL,
    website VARCHAR(300),
    country VARCHAR(80),
    contact_email VARCHAR(200) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    listing VARCHAR(20) NOT NULL DEFAULT 'preview',
    verification_tier VARCHAR(20) NOT NULL DEFAULT 'self_reported',
    plan VARCHAR(20) NOT NULL DEFAULT 'free',
    created_at TIMESTAMP DEFAULT NOW()
);

INSERT INTO tenants (slug, name, website, country, contact_email, status, listing, verification_tier)
VALUES ('creed-institute', 'C.R.E.E.D. Institute', 'https://creed-ai.org', 'Canada',
        'info@creed-ai.org', 'active', 'public', 'self_reported')
ON CONFLICT (slug) DO NOTHING;

ALTER TABLE governance_events ADD COLUMN IF NOT EXISTS tenant_id UUID;
ALTER TABLE incident_log ADD COLUMN IF NOT EXISTS tenant_id UUID;

UPDATE governance_events SET tenant_id = (SELECT id FROM tenants WHERE slug = 'creed-institute')
WHERE tenant_id IS NULL;
UPDATE incident_log SET tenant_id = (SELECT id FROM tenants WHERE slug = 'creed-institute')
WHERE tenant_id IS NULL;

DO $$
DECLARE inst UUID;
BEGIN
    SELECT id INTO inst FROM tenants WHERE slug = 'creed-institute';
    EXECUTE format('ALTER TABLE governance_events ALTER COLUMN tenant_id SET DEFAULT %L', inst);
    EXECUTE format('ALTER TABLE incident_log ALTER COLUMN tenant_id SET DEFAULT %L', inst);
    ALTER TABLE governance_events ALTER COLUMN tenant_id SET NOT NULL;
    ALTER TABLE incident_log ALTER COLUMN tenant_id SET NOT NULL;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_events_tenant') THEN
        ALTER TABLE governance_events
            ADD CONSTRAINT fk_events_tenant FOREIGN KEY (tenant_id) REFERENCES tenants(id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_incidents_tenant') THEN
        ALTER TABLE incident_log
            ADD CONSTRAINT fk_incidents_tenant FOREIGN KEY (tenant_id) REFERENCES tenants(id);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_events_tenant_created ON governance_events(tenant_id, created_at);
CREATE INDEX IF NOT EXISTS idx_incident_tenant ON incident_log(tenant_id);

-- P2.4 (#3905): self-serve onboarding fields. Applications land as
-- status='pending'; email verification + admin identity check (D1) gate
-- activation.
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS ai_description TEXT;
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS email_verified BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS verify_token VARCHAR(64);

-- P1.2: org-scoped API keys (Postgres-side; the legacy SQLite api_keys table
-- was never enforced and stays untouched for single-tenant self-hosters).
CREATE TABLE IF NOT EXISTS api_keys (
    id SERIAL PRIMARY KEY,
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    key_hash VARCHAR(64) UNIQUE NOT NULL,
    label VARCHAR(120),
    scopes VARCHAR(40) NOT NULL DEFAULT 'ingest',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW(),
    last_used_at TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_api_keys_tenant ON api_keys(tenant_id);
"""


def init_pg():
    global _pg_available
    if not Config.PG_HOST:
        logger.info("No PG_HOST configured — using SQLite fallback for events")
        return False
    try:
        conn = _get_pg_conn()
        cur = conn.cursor()
        cur.execute(SCHEMA)
        cur.execute(TENANT_MIGRATION)
        conn.commit()
        conn.close()
        _pg_available = True
        logger.info("Postgres initialized at %s:%s/%s", Config.PG_HOST, Config.PG_PORT, Config.PG_NAME)
        return True
    except Exception as e:
        logger.warning("Postgres unavailable, falling back to SQLite: %s", e)
        return False


def _get_pg_conn():
    return psycopg2.connect(
        host=Config.PG_HOST,
        port=Config.PG_PORT,
        dbname=Config.PG_NAME,
        user=Config.PG_USER,
        password=Config.pg_password(),
    )


def get_pg():
    global _pg_available
    # If PG is configured, attempt a real connection even when a prior init left
    # _pg_available False for THIS worker (a startup race with the PG container
    # leaves one gunicorn worker silently reading the empty SQLite fallback —
    # the cause of flaky "no rows" reads). Self-heals the flag on success.
    if not _pg_available and not Config.PG_HOST:
        return None
    try:
        conn = _get_pg_conn()
        _pg_available = True
        return conn
    except Exception as e:
        logger.error("Postgres connection failed: %s", e)
        return None


def is_pg_available():
    return _pg_available


_institute_tenant_id = None


def get_institute_tenant_id():
    """UUID (str) of the Institute's own tenant row. Cached per worker."""
    global _institute_tenant_id
    if _institute_tenant_id:
        return _institute_tenant_id
    conn = get_pg()
    if not conn:
        return None
    try:
        cur = conn.cursor()
        cur.execute("SELECT id FROM tenants WHERE slug = %s", (INSTITUTE_SLUG,))
        row = cur.fetchone()
        _institute_tenant_id = str(row[0]) if row else None
        return _institute_tenant_id
    finally:
        conn.close()
