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


def list_redress_requests(status=None, limit=200):
    """Return redress requests as dicts, soonest-SLA-due first (admin queue order).

    status=None returns every status; pass a value from STATUSES to filter.
    """
    where = "WHERE status = %s" if status else ""
    where_sqlite = "WHERE status = ?" if status else ""
    cols = (
        "request_ref, reason, ai_decision_ref, desired_outcome, email, status, "
        "resolution_notes, sla_due_at, resolved_at, created_at"
    )

    pg = get_pg()
    if pg:
        try:
            cur = pg.cursor()
            params = (status, limit) if status else (limit,)
            cur.execute(
                f"SELECT {cols} FROM redress_requests {where} "
                f"ORDER BY sla_due_at ASC LIMIT %s",
                params,
            )
            rows = cur.fetchall()
            col_names = [d[0] for d in cur.description]
            pg.close()
            return [_row_to_dict(dict(zip(col_names, r))) for r in rows]
        except Exception as e:
            logger.error("PG redress list failed, falling back to SQLite: %s", e)
            try:
                pg.close()
            except Exception:
                pass

    conn = get_db()
    try:
        params = (status, limit) if status else (limit,)
        rows = conn.execute(
            f"SELECT {cols} FROM redress_requests {where_sqlite} "
            f"ORDER BY sla_due_at ASC LIMIT ?",
            params,
        ).fetchall()
        return [_row_to_dict(dict(r)) for r in rows]
    finally:
        conn.close()


def _row_to_dict(d):
    for key in ("sla_due_at", "resolved_at", "created_at"):
        v = d.get(key)
        if v is not None and hasattr(v, "isoformat"):
            d[key] = v.isoformat()
    return d


def update_redress_status(request_ref, status, resolution_notes=""):
    """Transition a request's status. Sets resolved_at when landing on a
    terminal status (resolved/denied). Returns True if a row was updated."""
    if status not in STATUSES:
        raise ValueError(f"invalid status: {status}")
    resolved_now = status in ("resolved", "denied")

    pg = get_pg()
    if pg:
        try:
            cur = pg.cursor()
            if resolved_now:
                cur.execute(
                    "UPDATE redress_requests SET status=%s, resolution_notes=%s, "
                    "resolved_at=NOW() WHERE request_ref=%s",
                    (status, resolution_notes, request_ref),
                )
            else:
                cur.execute(
                    "UPDATE redress_requests SET status=%s, resolution_notes=%s "
                    "WHERE request_ref=%s",
                    (status, resolution_notes, request_ref),
                )
            updated = cur.rowcount > 0
            pg.commit()
            pg.close()
            return updated
        except Exception as e:
            logger.error("PG redress status update failed, falling back to SQLite: %s", e)
            try:
                pg.close()
            except Exception:
                pass

    conn = get_db()
    try:
        resolved_sql = "CURRENT_TIMESTAMP" if resolved_now else "resolved_at"
        cur = conn.execute(
            f"UPDATE redress_requests SET status=?, resolution_notes=?, "
            f"resolved_at={resolved_sql} WHERE request_ref=?",
            (status, resolution_notes, request_ref),
        )
        conn.commit()
        return cur.rowcount > 0
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
