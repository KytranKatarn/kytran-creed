import sqlite3
import os
import logging

logger = logging.getLogger(__name__)
_db_path = None


def init_db(path):
    global _db_path
    _db_path = path
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT,
            role TEXT DEFAULT 'viewer',
            display_name TEXT,
            email TEXT,
            sso_provider TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        );
        CREATE TABLE IF NOT EXISTS api_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key_hash TEXT UNIQUE NOT NULL,
            label TEXT,
            platform_name TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_active INTEGER DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            action TEXT,
            details TEXT,
            ip_address TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS governance_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT NOT NULL,
            source_platform TEXT NOT NULL,
            agent_id TEXT NOT NULL,
            agent_name TEXT,
            category TEXT NOT NULL,
            severity TEXT NOT NULL,
            description TEXT,
            metadata TEXT DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS incident_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            incident_ref TEXT UNIQUE NOT NULL,
            severity TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            affected_agents TEXT,
            root_cause TEXT,
            resolution TEXT,
            status TEXT NOT NULL DEFAULT 'investigating',
            lessons_learned TEXT,
            disclosed INTEGER NOT NULL DEFAULT 0,
            disclosed_at TIMESTAMP,
            occurred_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS tenants (
            id TEXT PRIMARY KEY,
            slug TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            website TEXT,
            country TEXT,
            contact_email TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            listing TEXT NOT NULL DEFAULT 'preview',
            verification_tier TEXT NOT NULL DEFAULT 'self_reported',
            plan TEXT NOT NULL DEFAULT 'free',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        INSERT OR IGNORE INTO tenants (id, slug, name, website, country, contact_email, status, listing)
        VALUES ('00000000-0000-0000-0000-000000000001', 'creed-institute', 'C.R.E.E.D. Institute',
                'https://creed-ai.org', 'Canada', 'info@creed-ai.org', 'active', 'public');
    """)
    # Multi-tenant columns (task #3269 P1.1). SQLite is the single-tenant /
    # self-host fallback, so tenant_id stays NULLABLE here (NULL = institute);
    # the NOT NULL contract is enforced on the multi-tenant Postgres path.
    for table in ("governance_events", "incident_log", "api_keys", "users"):
        _ensure_column(conn, table, "tenant_id", "TEXT REFERENCES tenants(id)")
    conn.execute(
        "UPDATE governance_events SET tenant_id = '00000000-0000-0000-0000-000000000001' WHERE tenant_id IS NULL"
    )
    conn.execute(
        "UPDATE incident_log SET tenant_id = '00000000-0000-0000-0000-000000000001' WHERE tenant_id IS NULL"
    )
    conn.commit()
    conn.close()
    logger.info("SQLite initialized at %s", path)


def _ensure_column(conn, table, column, ddl):
    """Idempotent ALTER TABLE ADD COLUMN for SQLite (no IF NOT EXISTS support)."""
    cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")


def get_db():
    conn = sqlite3.connect(_db_path)
    conn.row_factory = sqlite3.Row
    return conn
