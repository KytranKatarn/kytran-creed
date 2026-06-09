"""AI incident log — store + read (task #3263).

Proactive transparency: the platform files AI incidents (near-misses, errors,
unexpected behaviours) here; disclosed ones are published at
creed.kytranempowerment.com/incidents and mirrored to creed-ai.org/incidents.

Filing an incident never auto-publishes it — public visibility is gated by the
``disclosed`` flag (status.io-style). PG-first with a SQLite fallback, mirroring
``api_routes._store_event``.
"""

import logging

from kytran_creed.db import get_db
from kytran_creed.pg import get_pg

logger = logging.getLogger(__name__)

SEVERITIES = {"low", "medium", "high", "critical"}
STATUSES = {"investigating", "contained", "resolved", "monitoring"}

_INSERT_COLS = (
    "incident_ref, severity, title, description, affected_agents, root_cause, "
    "resolution, status, lessons_learned, disclosed, disclosed_at"
)


_SQLITE_INSTITUTE_TENANT = "00000000-0000-0000-0000-000000000001"


def store_incident(
    incident_ref,
    severity,
    title,
    description="",
    affected_agents="",
    root_cause="",
    resolution="",
    status="investigating",
    lessons_learned="",
    disclosed=False,
    tenant_id=None,
):
    """Insert an incident. Returns the new row id (or None on failure).

    tenant_id None = institute (PG column DEFAULT / SQLite fixed UUID) —
    task #3269 P1.2.
    """
    disclosed_at_sql = "NOW()" if disclosed else "NULL"
    vals = (
        incident_ref, severity, title, description, affected_agents, root_cause,
        resolution, status, lessons_learned, disclosed,
    )
    pg = get_pg()
    if pg:
        try:
            cur = pg.cursor()
            if tenant_id:
                cur.execute(
                    f"""INSERT INTO incident_log ({_INSERT_COLS}, tenant_id)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,{disclosed_at_sql},%s)
                        RETURNING id""",
                    vals + (tenant_id,),
                )
            else:
                cur.execute(
                    f"""INSERT INTO incident_log ({_INSERT_COLS})
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,{disclosed_at_sql})
                        RETURNING id""",
                    vals,
                )
            row = cur.fetchone()
            pg.commit()
            pg.close()
            return row[0]
        except Exception as e:
            logger.error("PG incident store failed, falling back to SQLite: %s", e)
            try:
                pg.close()
            except Exception:
                pass

    conn = get_db()
    try:
        sqlite_disclosed_at = "CURRENT_TIMESTAMP" if disclosed else "NULL"
        cur = conn.execute(
            f"""INSERT INTO incident_log ({_INSERT_COLS}, tenant_id)
                VALUES (?,?,?,?,?,?,?,?,?,?,{sqlite_disclosed_at},?)""",
            vals + (tenant_id or _SQLITE_INSTITUTE_TENANT,),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def list_incidents(disclosed_only=True, limit=100):
    """Return incidents as a list of dicts, newest first."""
    where = "WHERE disclosed = TRUE" if disclosed_only else ""
    cols = (
        "incident_ref, severity, title, description, affected_agents, root_cause, "
        "resolution, status, lessons_learned, disclosed, disclosed_at, occurred_at"
    )
    pg = get_pg()
    if pg:
        try:
            cur = pg.cursor()
            cur.execute(
                f"SELECT {cols} FROM incident_log {where} "
                f"ORDER BY COALESCE(disclosed_at, occurred_at, created_at) DESC LIMIT %s",
                (limit,),
            )
            rows = cur.fetchall()
            col_names = [d[0] for d in cur.description]
            pg.close()
            return [_row_to_dict(dict(zip(col_names, r))) for r in rows]
        except Exception as e:
            logger.error("PG incident list failed, falling back to SQLite: %s", e)
            try:
                pg.close()
            except Exception:
                pass

    where_sqlite = "WHERE disclosed = 1" if disclosed_only else ""
    conn = get_db()
    try:
        cur = conn.execute(
            f"SELECT {cols} FROM incident_log {where_sqlite} "
            f"ORDER BY COALESCE(disclosed_at, occurred_at, created_at) DESC LIMIT ?",
            (limit,),
        )
        return [_row_to_dict(dict(row)) for row in cur.fetchall()]
    finally:
        conn.close()


def _row_to_dict(d):
    """Normalise a DB row dict for JSON (stringify timestamps)."""
    for k in ("disclosed_at", "occurred_at"):
        if d.get(k) is not None and not isinstance(d[k], str):
            d[k] = d[k].isoformat()
    d["disclosed"] = bool(d.get("disclosed"))
    return d
