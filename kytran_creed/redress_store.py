"""AI-decision redress requests — store + public read (creed-ai.org /accountability.html).

A visitor who believes an AI-driven decision was wrong can file a redress
request. Filing never auto-resolves it — a human reviewer works the queue
(status: pending -> under_review -> resolved|denied) same as incident
disclosure is gated by ``disclosed`` in incident_store.py. PG-first with a
SQLite fallback, mirroring incident_store.py's connection pattern.
"""

import logging
from datetime import datetime, timedelta

from kytran_creed.db import get_db
from kytran_creed.pg import get_pg

logger = logging.getLogger(__name__)

STATUSES = {"pending", "under_review", "resolved", "denied"}
SLA_BUSINESS_DAYS = 5

_INSERT_COLS = "request_ref, reason, ai_decision_ref, desired_outcome, email, status, sla_due_at"


def _add_business_days(start: datetime, n: int) -> datetime:
    """Add n business days (Mon-Fri) to start, skipping weekends."""
    d = start
    added = 0
    while added < n:
        d += timedelta(days=1)
        if d.weekday() < 5:  # Mon=0 .. Fri=4
            added += 1
    return d


def store_redress_request(request_ref, reason, ai_decision_ref="", desired_outcome="", email=""):
    """Insert a pending redress request. Returns (id, sla_due_at) or (None, None) on failure."""
    sla_due_at = _add_business_days(datetime.utcnow(), SLA_BUSINESS_DAYS)
    vals = (request_ref, reason, ai_decision_ref, desired_outcome, email, "pending", sla_due_at)

    pg = get_pg()
    if pg:
        try:
            cur = pg.cursor()
            cur.execute(
                f"INSERT INTO redress_requests ({_INSERT_COLS}) VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                vals,
            )
            row = cur.fetchone()
            pg.commit()
            pg.close()
            return row[0], sla_due_at
        except Exception as e:
            logger.error("PG redress store failed, falling back to SQLite: %s", e)
            try:
                pg.close()
            except Exception:
                pass

    conn = get_db()
    try:
        cur = conn.execute(
            f"INSERT INTO redress_requests ({_INSERT_COLS}) VALUES (?,?,?,?,?,?,?)",
            vals,
        )
        conn.commit()
        return cur.lastrowid, sla_due_at
    finally:
        conn.close()


def get_redress_stats():
    """Return {total, by_status, avg_resolution_days, sla_business_days, resolution_is_human}."""
    pg = get_pg()
    if pg:
        try:
            cur = pg.cursor()
            cur.execute("SELECT status, COUNT(*) FROM redress_requests GROUP BY status")
            by_status_rows = cur.fetchall()
            cur.execute(
                "SELECT AVG(EXTRACT(EPOCH FROM (resolved_at - created_at)) / 86400.0) "
                "FROM redress_requests WHERE resolved_at IS NOT NULL"
            )
            avg_row = cur.fetchone()
            pg.close()
            return _shape_stats(by_status_rows, avg_row[0] if avg_row else None)
        except Exception as e:
            logger.error("PG redress stats failed, falling back to SQLite: %s", e)
            try:
                pg.close()
            except Exception:
                pass

    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT status, COUNT(*) AS c FROM redress_requests GROUP BY status"
        ).fetchall()
        by_status_rows = [(r["status"], r["c"]) for r in rows]
        avg_row = conn.execute(
            "SELECT AVG(julianday(resolved_at) - julianday(created_at)) AS a "
            "FROM redress_requests WHERE resolved_at IS NOT NULL"
        ).fetchone()
        return _shape_stats(by_status_rows, avg_row["a"] if avg_row else None)
    finally:
        conn.close()


def _shape_stats(by_status_rows, avg_days):
    by_status = {"pending": 0, "under_review": 0, "resolved": 0, "denied": 0}
    for status, count in by_status_rows:
        if status in by_status:
            by_status[status] = int(count)
    total = sum(by_status.values())
    return {
        "total": total,
        "by_status": by_status,
        "avg_resolution_days": round(avg_days, 1) if avg_days is not None else None,
        "sla_business_days": SLA_BUSINESS_DAYS,
        "resolution_is_human": True,
    }
