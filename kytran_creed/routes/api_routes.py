import json
import logging
from datetime import datetime, timedelta
from flask import Blueprint, jsonify, render_template, request

from kytran_creed.db import get_db
from kytran_creed.models import GovernanceEvent
from kytran_creed.pg import get_pg, is_pg_available
from kytran_creed.services.scoring_engine import calculate_scores

logger = logging.getLogger(__name__)
api_bp = Blueprint("api", __name__, url_prefix="/api/v1")


_SQLITE_INSTITUTE_TENANT = "00000000-0000-0000-0000-000000000001"


def _store_event(event: GovernanceEvent, tenant_id: str | None = None) -> int:
    """Try PG first, fall back to SQLite. Returns new event id.

    tenant_id None = institute (PG column DEFAULT / SQLite fixed UUID).
    """
    metadata_str = json.dumps(event.metadata)
    base_vals = (
        event.event_type,
        event.source_platform,
        event.agent_id,
        event.agent_name,
        event.category,
        event.severity,
        event.description,
        metadata_str,
    )
    pg = get_pg()
    if pg:
        try:
            cur = pg.cursor()
            if tenant_id:
                cur.execute(
                    """INSERT INTO governance_events
                       (event_type, source_platform, agent_id, agent_name, category, severity, description, metadata, tenant_id)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
                    base_vals + (tenant_id,),
                )
            else:
                cur.execute(
                    """INSERT INTO governance_events
                       (event_type, source_platform, agent_id, agent_name, category, severity, description, metadata)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
                    base_vals,
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
               (event_type, source_platform, agent_id, agent_name, category, severity, description, metadata, tenant_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            base_vals + (tenant_id or _SQLITE_INSTITUTE_TENANT,),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def _get_recent_events(days: int = 30, tenant_id: str | None = None) -> list[dict]:
    """Fetch events from the last N days for scoring (optionally tenant-scoped)."""
    pg = get_pg()
    if pg:
        try:
            sql = "SELECT category, severity FROM governance_events WHERE created_at >= NOW() - INTERVAL '%s days'"
            params: list = [days]
            if tenant_id:
                sql += " AND tenant_id = %s"
                params.append(tenant_id)
            cur = pg.cursor()
            cur.execute(sql, params)
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
        sql = "SELECT category, severity FROM governance_events WHERE created_at >= ?"
        params = [since]
        if tenant_id:
            sql += " AND tenant_id = ?"
            params.append(tenant_id)
        cur = conn.execute(sql, params)
        rows = cur.fetchall()
        return [{"category": row["category"], "severity": row["severity"]} for row in rows]
    finally:
        conn.close()


@api_bp.route("/docs")
def api_docs():
    return render_template("api_docs.html")


@api_bp.route("/events", methods=["POST"])
def post_event():
    # P1.2 (#3269): Bearer creed_sk_* key → tenant-scoped ingest. No key =
    # institute fallback (the hub's LAN feed — switches to a key in P2).
    from kytran_creed.tenant_auth import ingest_guard, keyless_rejected, resolve_tenant

    tenant_id, auth_err = resolve_tenant()
    if auth_err:
        return auth_err
    if tenant_id is None:
        rejected = keyless_rejected()
        if rejected:
            return rejected

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

    # PII firewall + metadata cap on EXTERNAL (key-authenticated) ingest only —
    # the institute's legacy keyless feed is exempt until it migrates in P2.
    if tenant_id:
        guard_err = ingest_guard(event.description, json.dumps(event.metadata))
        if guard_err:
            return guard_err

    event_id = _store_event(event, tenant_id)
    return jsonify({"success": True, "event_id": event_id}), 201


@api_bp.route("/incidents", methods=["POST"])
def post_incident():
    """File an AI incident (task #3263).

    Filing does NOT auto-publish — public visibility is gated by ``disclosed``.
    Body: {severity (low/medium/high/critical), title, description?,
    affected_agents?, root_cause?, resolution?, status?, lessons_learned?,
    disclosed?}.
    """
    import uuid

    from kytran_creed.incident_store import SEVERITIES, STATUSES, store_incident
    from kytran_creed.tenant_auth import keyless_rejected, resolve_tenant

    tenant_id, auth_err = resolve_tenant()
    if auth_err:
        return auth_err
    if tenant_id is None:
        rejected = keyless_rejected()
        if rejected:
            return rejected

    data = request.get_json(force=True, silent=True) or {}
    severity = (data.get("severity") or "").strip().lower()
    title = (data.get("title") or "").strip()
    if severity not in SEVERITIES:
        return (
            jsonify({"success": False, "error": f"severity must be one of {sorted(SEVERITIES)}"}),
            400,
        )
    if not title or len(title) > 300:
        return jsonify({"success": False, "error": "title required (<=300 chars)"}), 400

    status = (data.get("status") or "investigating").strip().lower()
    if status not in STATUSES:
        status = "investigating"

    aff = data.get("affected_agents")
    if isinstance(aff, list):
        aff = ", ".join(str(a) for a in aff)

    incident_ref = (data.get("incident_ref") or ("INC-" + uuid.uuid4().hex[:8])).strip()
    disclosed = bool(data.get("disclosed", False))

    iid = store_incident(
        incident_ref=incident_ref,
        severity=severity,
        title=title,
        description=(data.get("description") or ""),
        affected_agents=(aff or ""),
        root_cause=(data.get("root_cause") or ""),
        resolution=(data.get("resolution") or ""),
        status=status,
        lessons_learned=(data.get("lessons_learned") or ""),
        disclosed=disclosed,
        tenant_id=tenant_id,
    )
    if iid is None:
        return jsonify({"success": False, "error": "incident store failed"}), 500
    return (
        jsonify({"success": True, "incident_ref": incident_ref, "id": iid, "disclosed": disclosed}),
        201,
    )


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
    # P1.2: this global endpoint is now an ALIAS for the Institute tenant
    # (tenant #1). Per-org scores live at /api/v1/orgs/<slug>/scores. When PG
    # is unavailable the institute id is None → unfiltered, same as before.
    from kytran_creed.pg import get_institute_tenant_id

    days = int(request.args.get("days", 30))
    events = _get_recent_events(days, get_institute_tenant_id())
    scores = calculate_scores(events)
    # CORS-open + short-cached so public sites (creed-ai.org governance widget)
    # can consume the per-category breakdown cross-origin — mirrors /api/public/score.
    return (
        jsonify(scores),
        200,
        {
            "Cache-Control": "public, max-age=60",
            "Access-Control-Allow-Origin": "*",
        },
    )
