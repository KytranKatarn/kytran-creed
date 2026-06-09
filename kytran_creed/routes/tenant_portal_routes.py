"""Org-admin portal — tenant-scoped dashboard (PR B / P2.5).

A tenant org admin authenticates at /org-admin/login with their API key.
Session keys (tp_* prefix, separate from Flask-Login institute auth):
  session['tp_tenant_id'], session['tp_slug'], session['tp_name']

Routes:
  GET  /org-admin/login        login page
  POST /org-admin/login        validate key → set session
  GET  /org-admin/logout       clear session
  GET  /org-admin/dashboard    scoped overview (score, events, keys)
  POST /org-admin/api/keys     mint new key (returned plaintext, shown once)
  POST /org-admin/api/keys/<id>/revoke  revoke own key
"""

import hashlib
import logging

from flask import Blueprint, jsonify, redirect, render_template, request, session

from kytran_creed.pg import get_pg
from kytran_creed.services.scoring_engine import GRADE_THRESHOLDS, calculate_scores
from kytran_creed.tenant_auth import KEY_PREFIX, generate_api_key

logger = logging.getLogger(__name__)
tenant_portal_bp = Blueprint("tenant_portal", __name__)

_SESSION_KEY = "tp_tenant_id"


def _hash_key(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def _current_tenant():
    return session.get(_SESSION_KEY), session.get("tp_slug"), session.get("tp_name")


def tenant_admin_required(f):
    from functools import wraps

    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get(_SESSION_KEY):
            return redirect("/org-admin/login")
        return f(*args, **kwargs)

    return decorated


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


@tenant_portal_bp.route("/org-admin/login", methods=["GET"])
def tp_login_page():
    if session.get(_SESSION_KEY):
        return redirect("/org-admin/dashboard")
    return render_template("tenant_login.html")


@tenant_portal_bp.route("/org-admin/login", methods=["POST"])
def tp_login():
    data = request.get_json(silent=True) or {}
    api_key = (data.get("api_key") or "").strip()
    if not api_key.startswith(KEY_PREFIX):
        return jsonify({"success": False, "error": "Key must start with creed_sk_"}), 401

    pg = get_pg()
    if not pg:
        return jsonify({"success": False, "error": "Database unavailable"}), 503

    key_hash = _hash_key(api_key)
    try:
        cur = pg.cursor()
        cur.execute(
            """SELECT k.tenant_id, t.slug, t.name, t.status
               FROM api_keys k JOIN tenants t ON t.id = k.tenant_id
               WHERE k.key_hash = %s AND k.is_active""",
            (key_hash,),
        )
        row = cur.fetchone()
        if not row:
            return jsonify({"success": False, "error": "Invalid or inactive API key"}), 401
        tenant_id, slug, name, status = str(row[0]), row[1], row[2], row[3]
        if status != "active":
            return jsonify({"success": False, "error": f"Tenant status '{status}' — not approved"}), 403
        cur.execute("UPDATE api_keys SET last_used_at = NOW() WHERE key_hash = %s", (key_hash,))
        pg.commit()
        session[_SESSION_KEY] = tenant_id
        session["tp_slug"] = slug
        session["tp_name"] = name
        session.permanent = True
        return jsonify({"success": True, "slug": slug})
    except Exception as e:
        logger.error("tenant portal login failed: %s", e)
        return jsonify({"success": False, "error": "Auth backend unavailable"}), 503
    finally:
        try:
            pg.close()
        except Exception:
            pass


@tenant_portal_bp.route("/org-admin/logout")
def tp_logout():
    session.pop(_SESSION_KEY, None)
    session.pop("tp_slug", None)
    session.pop("tp_name", None)
    return redirect("/org-admin/login")


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


@tenant_portal_bp.route("/org-admin/dashboard")
@tenant_admin_required
def tp_dashboard():
    tenant_id, slug, name = _current_tenant()

    pg = get_pg()
    if not pg:
        return render_template(
            "tenant_dashboard.html", error="Database unavailable", name=name, slug=slug, data=None
        )

    try:
        cur = pg.cursor()

        # All events for scoring
        cur.execute(
            "SELECT category, severity FROM governance_events WHERE tenant_id = %s",
            (tenant_id,),
        )
        event_rows = cur.fetchall()
        events_for_score = [{"category": r[0], "severity": r[1]} for r in event_rows]
        score_data = calculate_scores(events_for_score)

        # Provisional gate (≥100 events, ≥3 categories, ≥14 days span)
        cur.execute(
            """SELECT COUNT(*), COUNT(DISTINCT category), MIN(created_at), MAX(created_at)
               FROM governance_events WHERE tenant_id = %s""",
            (tenant_id,),
        )
        r = cur.fetchone()
        event_count = r[0] or 0
        category_count = r[1] or 0
        first_event, last_event = r[2], r[3]
        span_days = (last_event - first_event).days if first_event and last_event else 0

        provisional = event_count < 100 or category_count < 3 or span_days < 14
        provisional_gaps = []
        if event_count < 100:
            provisional_gaps.append(f"{event_count}/100 events")
        if category_count < 3:
            provisional_gaps.append(f"{category_count}/3 categories")
        if span_days < 14:
            provisional_gaps.append(f"{span_days}/14 days span")

        # Events in last 30 days
        cur.execute(
            """SELECT COUNT(*) FROM governance_events
               WHERE tenant_id = %s AND created_at > NOW() - INTERVAL '30 days'""",
            (tenant_id,),
        )
        events_30d = cur.fetchone()[0] or 0

        # Recent 10 events
        cur.execute(
            """SELECT event_type, source_platform, category, severity, description, created_at
               FROM governance_events WHERE tenant_id = %s
               ORDER BY created_at DESC LIMIT 10""",
            (tenant_id,),
        )
        recent_events = [
            {
                "event_type": r[0],
                "source_platform": r[1],
                "category": r[2],
                "severity": r[3],
                "description": r[4],
                "created_at": r[5],
            }
            for r in cur.fetchall()
        ]

        # API keys (no hash exposed)
        cur.execute(
            """SELECT id, scopes, is_active, created_at, last_used_at
               FROM api_keys WHERE tenant_id = %s ORDER BY created_at DESC""",
            (tenant_id,),
        )
        keys = [
            {
                "id": str(r[0]),
                "scopes": r[1],
                "is_active": r[2],
                "created_at": r[3],
                "last_used_at": r[4],
            }
            for r in cur.fetchall()
        ]

        # Open incidents
        cur.execute(
            "SELECT COUNT(*) FROM incident_log WHERE tenant_id = %s AND status = 'open'",
            (tenant_id,),
        )
        open_incidents = cur.fetchone()[0] or 0

        data = {
            "score_data": score_data,
            "provisional": provisional,
            "provisional_gaps": provisional_gaps,
            "event_count": event_count,
            "events_30d": events_30d,
            "last_event": last_event,
            "open_incidents": open_incidents,
            "recent_events": recent_events,
            "keys": keys,
        }
        return render_template("tenant_dashboard.html", name=name, slug=slug, data=data, error=None)

    except Exception as e:
        logger.error("tenant portal dashboard failed: %s", e)
        return render_template(
            "tenant_dashboard.html", error=str(e), name=name, slug=slug, data=None
        )
    finally:
        try:
            pg.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Key management API
# ---------------------------------------------------------------------------


@tenant_portal_bp.route("/org-admin/api/keys", methods=["POST"])
@tenant_admin_required
def tp_mint_key():
    tenant_id, _, _ = _current_tenant()
    pg = get_pg()
    if not pg:
        return jsonify({"success": False, "error": "Database unavailable"}), 503
    try:
        plaintext, key_hash = generate_api_key()
        cur = pg.cursor()
        cur.execute(
            """INSERT INTO api_keys (tenant_id, key_hash, scopes, is_active)
               VALUES (%s, %s, 'ingest', TRUE) RETURNING id""",
            (tenant_id, key_hash),
        )
        key_id = str(cur.fetchone()[0])
        pg.commit()
        # Plaintext returned once — never stored, never shown again
        return jsonify({"success": True, "key": plaintext, "key_id": key_id})
    except Exception as e:
        logger.error("tenant portal mint key failed: %s", e)
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        try:
            pg.close()
        except Exception:
            pass


@tenant_portal_bp.route("/org-admin/api/keys/<key_id>/revoke", methods=["POST"])
@tenant_admin_required
def tp_revoke_key(key_id):
    tenant_id, _, _ = _current_tenant()
    pg = get_pg()
    if not pg:
        return jsonify({"success": False, "error": "Database unavailable"}), 503
    try:
        cur = pg.cursor()
        # Ownership check — only revoke own keys
        cur.execute(
            "UPDATE api_keys SET is_active = FALSE WHERE id = %s AND tenant_id = %s RETURNING id",
            (key_id, tenant_id),
        )
        if not cur.fetchone():
            pg.rollback()
            return jsonify({"success": False, "error": "Key not found or not owned by your org"}), 404
        pg.commit()
        return jsonify({"success": True})
    except Exception as e:
        logger.error("tenant portal revoke key failed: %s", e)
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        try:
            pg.close()
        except Exception:
            pass
