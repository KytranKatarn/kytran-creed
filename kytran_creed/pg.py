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
"""


def init_pg():
    global _pg_available
    if not Config.PG_HOST:
        logger.info("No PG_HOST configured — using SQLite fallback for events")
        return False
    try:
        conn = _get_pg_conn()
        conn.cursor().execute(SCHEMA)
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
