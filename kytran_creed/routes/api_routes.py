import json
import logging
from datetime import datetime, timedelta
from flask import Blueprint, jsonify, request

from kytran_creed.db import get_db
from kytran_creed.models import GovernanceEvent
from kytran_creed.pg import get_pg, is_pg_available
from kytran_creed.services.scoring_engine import calculate_scores

logger = logging.getLogger(__name__)
api_bp = Blueprint("api", __name__, url_prefix="/api/v1")


def _store_event(event: GovernanceEvent) -> int:
    """Try PG first, fall back to SQLite. Returns new event id."""
    metadata_str = json.dumps(event.metadata)
    pg = get_pg()
    if pg:
        try:
            cur = pg.cursor()
            cur.execute(
                """INSERT INTO governance_events
                   (event_type, source_platform, agent_id, agent_name, category, severity, description, metadata)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
                (
                    event.event_type,
                    event.source_platform,
                    event.agent_id,
                    event.agent_name,
                    event.category,
                    event.severity,
                    event.description,
                    metadata_str,
                ),
            )
            row = cur.fetchone()
            pg.commit()
            pg.close()
            return row[0]
        except Exception as e:
            logger.error("PG store failed, falling back to SQLite: %s", e)
            try:
                pg.close()
            except Exception:
                pass

    # SQLite fallback
    conn = get_db()
    try:
        cur = conn.execute(
            """INSERT INTO governance_events
               (event_type, source_platform, agent_id, agent_name, category, severity, description, metadata)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                event.event_type,
                event.source_platform,
                event.agent_id,
                event.agent_name,
                event.category,
                event.severity,
                event.description,
                metadata_str,
            ),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def _get_recent_events(days: int = 30) -> list[dict]:
    """Fetch events from the last N days for scoring."""
    pg = get_pg()
    if pg:
        try:
            cur = pg.cursor()
            cur.execute(
                "SELECT category, severity FROM governance_events WHERE created_at >= NOW() - INTERVAL '%s days'",
                (days,),
            )
            rows = cur.fetchall()
            pg.close()
            return [{"category": r[0], "severity": r[1]} for r in rows]
        except Exception as e:
            logger.error("PG fetch failed, falling back to SQLite: %s", e)
            try:
                pg.close()
            except Exception:
                pass

    # SQLite fallback
    conn = get_db()
    try:
        since = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
        cur = conn.execute(
            "SELECT category, severity FROM governance_events WHERE created_at >= ?",
            (since,),
        )
        rows = cur.fetchall()
        return [{"category": row["category"], "severity": row["severity"]} for row in rows]
    finally:
        conn.close()


@api_bp.route("/events", methods=["POST"])
def post_event():
    data = request.get_json(force=True, silent=True) or {}
    event = GovernanceEvent(
        event_type=data.get("event_type", ""),
        source_platform=data.get("source_platform", ""),
        agent_id=data.get("agent_id", ""),
        agent_name=data.get("agent_name", ""),
        category=data.get("category", ""),
        severity=data.get("severity", ""),
        description=data.get("description", ""),
        metadata=data.get("metadata", {}),
    )
    errors = event.validate()
    if errors:
        return jsonify({"success": False, "errors": errors}), 400

    event_id = _store_event(event)
    return jsonify({"success": True, "event_id": event_id}), 201


@api_bp.route("/events", methods=["GET"])
def get_events():
    category = request.args.get("category")
    severity = request.args.get("severity")
    limit = min(int(request.args.get("limit", 50)), 500)
    offset = int(request.args.get("offset", 0))

    pg = get_pg()
    if pg:
        try:
            conditions = []
            params = []
            if category:
                conditions.append("category = %s")
                params.append(category)
            if severity:
                conditions.append("severity = %s")
                params.append(severity)
            where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
            params += [limit, offset]
            cur = pg.cursor()
            cur.execute(
                f"SELECT id, event_type, source_platform, agent_id, agent_name, category, severity, description, created_at FROM governance_events {where} ORDER BY created_at DESC LIMIT %s OFFSET %s",
                params,
            )
            cols = [d[0] for d in cur.description]
            rows = [dict(zip(cols, row)) for row in cur.fetchall()]
            pg.close()
            return jsonify({"events": rows, "limit": limit, "offset": offset})
        except Exception as e:
            logger.error("PG list failed, falling back to SQLite: %s", e)
            try:
                pg.close()
            except Exception:
                pass

    # SQLite fallback
    conn = get_db()
    try:
        conditions = []
        params = []
        if category:
            conditions.append("category = ?")
            params.append(category)
        if severity:
            conditions.append("severity = ?")
            params.append(severity)
        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        params += [limit, offset]
        cur = conn.execute(
            f"SELECT id, event_type, source_platform, agent_id, agent_name, category, severity, description, created_at FROM governance_events {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            params,
        )
        rows = [dict(row) for row in cur.fetchall()]
        return jsonify({"events": rows, "limit": limit, "offset": offset})
    finally:
        conn.close()


@api_bp.route("/audit", methods=["GET"])
def get_audit():
    limit = min(int(request.args.get("limit", 50)), 500)
    offset = int(request.args.get("offset", 0))

    conn = get_db()
    try:
        cur = conn.execute(
            "SELECT id, user_id, action, details, ip_address, created_at FROM audit_log ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        )
        entries = [dict(row) for row in cur.fetchall()]
        return jsonify({"entries": entries, "limit": limit, "offset": offset})
    finally:
        conn.close()


@api_bp.route("/scores", methods=["GET"])
def get_scores():
    days = int(request.args.get("days", 30))
    events = _get_recent_events(days)
    scores = calculate_scores(events)
    return jsonify(scores)
