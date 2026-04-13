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
    if not _pg_available:
        return None
    try:
        return _get_pg_conn()
    except Exception as e:
        logger.error("Postgres connection failed: %s", e)
        return None


def is_pg_available():
    return _pg_available
