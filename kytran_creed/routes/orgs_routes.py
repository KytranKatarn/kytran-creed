"""Multi-tenant org directory + per-tenant scores + admin tenant/key management.

Task #3269 P1.2 (ADR-004). All endpoints require Postgres (multi-tenant mode);
SQLite single-tenant deployments get a 503 here and keep the legacy global
endpoints, which now alias the Institute tenant.

Public (CORS-open):
  GET /api/v1/orgs                  — directory of active+public tenants
  GET /api/v1/orgs/<slug>/scores    — per-tenant scores + provisional gate + freshness

Admin (institute, @admin_required):
  POST /api/v1/orgs                 — create a tenant
  POST /api/v1/orgs/<slug>/keys     — mint an API key (plaintext returned ONCE)
  GET  /api/v1/orgs/<slug>/keys     — list key metadata (never plaintext/hash)
"""

import logging
import re

from flask import Blueprint, jsonify, request

from kytran_creed.auth import admin_required
from kytran_creed.pg import get_pg
from kytran_creed.routes.api_routes import _get_recent_events
from kytran_creed.services.scoring_engine import calculate_scores
from kytran_creed.tenant_auth import generate_api_key

logger = logging.getLogger(__name__)
orgs_bp = Blueprint("orgs", __name__, url_prefix="/api/v1")

# Provisional gate (ADR-004 §5): no real score until the feed has substance.
PROVISIONAL_MIN_EVENTS = 100
PROVISIONAL_MIN_CATEGORIES = 3
PROVISIONAL_MIN_SPAN_DAYS = 14

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,78}[a-z0-9]$")
_PUBLIC_FIELDS = "id, slug, name, website, country, status, listing, verification_tier, created_at"


def _no_pg():
    return jsonify({"success": False, "error": "multi-tenant mode requires Postgres"}), 503


def _tenant_row_to_dict(row):
    return {
        "slug": row[1],
        "name": row[2],
        "website": row[3],
        "country": row[4],
        "status": row[5],
        "listing": row[6],
        "verification_tier": row[7],
        "member_since": row[8].isoformat() if row[8] else None,
    }


def _get_public_tenant(pg, slug):
    cur = pg.cursor()
    cur.execute(
        f"SELECT {_PUBLIC_FIELDS} FROM tenants WHERE slug = %s AND status = 'active' AND listing = 'public'",
        (slug,),
    )
    return cur.fetchone()


def _tenant_stats(pg, tenant_id):
    """Provisional gate + freshness numbers for one tenant."""
    cur = pg.cursor()
    cur.execute(
        """SELECT COUNT(*),
                  COUNT(DISTINCT category),
                  COALESCE(EXTRACT(EPOCH FROM (MAX(created_at) - MIN(created_at))) / 86400.0, 0),
                  MAX(created_at),
                  COUNT(*) FILTER (WHERE created_at >= NOW() - INTERVAL '30 days')
           FROM governance_events WHERE tenant_id = %s""",
        (tenant_id,),
    )
    total, cats, span_days, last_at, ev30 = cur.fetchone()
    provisional = not (
        total >= PROVISIONAL_MIN_EVENTS
        and cats >= PROVISIONAL_MIN_CATEGORIES
        and float(span_days or 0) >= PROVISIONAL_MIN_SPAN_DAYS
    )
    return {
        "provisional": provisional,
        "total_events": int(total or 0),
        "categories_active": int(cats or 0),
        "span_days": round(float(span_days or 0), 1),
        "last_event_at": last_at.isoformat() if last_at else None,
        "events_30d": int(ev30 or 0),
    }


@orgs_bp.route("/orgs", methods=["GET"])
def list_orgs():
    """Public directory of active + publicly-listed tenants."""
    pg = get_pg()
    if not pg:
        return _no_pg()
    try:
        cur = pg.cursor()
        cur.execute(
            f"SELECT {_PUBLIC_FIELDS} FROM tenants WHERE status = 'active' AND listing = 'public' ORDER BY created_at"
        )
        rows = cur.fetchall()
        orgs = []
        for row in rows:
            tenant_id = str(row[0])
            entry = _tenant_row_to_dict(row)
            stats = _tenant_stats(pg, tenant_id)
            scores = calculate_scores(_get_recent_events(30, tenant_id))
            entry.update(
                {
                    "overall": None if stats["provisional"] else scores.get("overall"),
                    "grade": "PROVISIONAL" if stats["provisional"] else scores.get("grade"),
                    "provisional": stats["provisional"],
                    "last_event_at": stats["last_event_at"],
                    "events_30d": stats["events_30d"],
                }
            )
            orgs.append(entry)
        pg.close()
        return (
            jsonify({"orgs": orgs, "count": len(orgs)}),
            200,
            {"Cache-Control": "public, max-age=300", "Access-Control-Allow-Origin": "*"},
        )
    except Exception as e:
        logger.error("org directory failed: %s", e)
        try:
            pg.close()
        except Exception:
            pass
        return jsonify({"success": False, "error": "directory unavailable"}), 500


@orgs_bp.route("/orgs/<slug>/scores", methods=["GET"])
def org_scores(slug):
    """Per-tenant scores — same shape as /api/v1/scores plus tenant context,
    the provisional gate, and freshness (ADR-004 §5)."""
    pg = get_pg()
    if not pg:
        return _no_pg()
    try:
        row = _get_public_tenant(pg, slug)
        if not row:
            pg.close()
            return jsonify({"success": False, "error": "unknown org"}), 404
        tenant_id = str(row[0])
        stats = _tenant_stats(pg, tenant_id)
        pg.close()
        days = int(request.args.get("days", 30))
        scores = calculate_scores(_get_recent_events(days, tenant_id))
        if stats["provisional"]:
            scores["grade"] = "PROVISIONAL"
        scores["tenant"] = _tenant_row_to_dict(row)
        scores["freshness"] = stats
        return (
            jsonify(scores),
            200,
            {"Cache-Control": "public, max-age=60", "Access-Control-Allow-Origin": "*"},
        )
    except Exception as e:
        logger.error("org scores failed for %s: %s", slug, e)
        try:
            pg.close()
        except Exception:
            pass
        return jsonify({"success": False, "error": "scores unavailable"}), 500


@orgs_bp.route("/orgs", methods=["POST"])
@admin_required
def create_org():
    """Create a tenant (institute admin only — self-serve onboarding is P2).

    Body: {slug, name, contact_email, website?, country?, status?, listing?}.
    D1: real-org identity verified by the admin before status='active'.
    """
    pg = get_pg()
    if not pg:
        return _no_pg()
    data = request.get_json(force=True, silent=True) or {}
    slug = (data.get("slug") or "").strip().lower()
    name = (data.get("name") or "").strip()
    contact_email = (data.get("contact_email") or "").strip()
    if not _SLUG_RE.match(slug):
        return jsonify({"success": False, "error": "slug must be 3-80 chars [a-z0-9-]"}), 400
    if not name or not contact_email:
        return jsonify({"success": False, "error": "name and contact_email required"}), 400
    status = data.get("status", "pending")
    listing = data.get("listing", "preview")
    if status not in ("pending", "active", "suspended") or listing not in ("preview", "public"):
        return jsonify({"success": False, "error": "invalid status/listing"}), 400
    try:
        cur = pg.cursor()
        cur.execute(
            """INSERT INTO tenants (slug, name, website, country, contact_email, status, listing)
               VALUES (%s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (slug) DO NOTHING RETURNING id""",
            (slug, name, data.get("website"), data.get("country"), contact_email, status, listing),
        )
        row = cur.fetchone()
        pg.commit()
        pg.close()
        if not row:
            return jsonify({"success": False, "error": "slug already exists"}), 409
        return jsonify({"success": True, "tenant_id": str(row[0]), "slug": slug}), 201
    except Exception as e:
        logger.error("create org failed: %s", e)
        try:
            pg.close()
        except Exception:
            pass
        return jsonify({"success": False, "error": "create failed"}), 500


@orgs_bp.route("/orgs/<slug>/keys", methods=["POST"])
@admin_required
def mint_org_key(slug):
    """Mint an ingest API key for a tenant. Plaintext is returned ONCE."""
    pg = get_pg()
    if not pg:
        return _no_pg()
    try:
        cur = pg.cursor()
        cur.execute("SELECT id FROM tenants WHERE slug = %s", (slug,))
        row = cur.fetchone()
        if not row:
            pg.close()
            return jsonify({"success": False, "error": "unknown org"}), 404
        data = request.get_json(force=True, silent=True) or {}
        plaintext, key_hash = generate_api_key()
        cur.execute(
            "INSERT INTO api_keys (tenant_id, key_hash, label) VALUES (%s, %s, %s) RETURNING id",
            (row[0], key_hash, (data.get("label") or "ingest")[:120]),
        )
        key_id = cur.fetchone()[0]
        pg.commit()
        pg.close()
        return (
            jsonify(
                {
                    "success": True,
                    "key_id": key_id,
                    "api_key": plaintext,
                    "note": "Store this now — it is shown exactly once and only its hash is kept.",
                }
            ),
            201,
        )
    except Exception as e:
        logger.error("mint key failed for %s: %s", slug, e)
        try:
            pg.close()
        except Exception:
            pass
        return jsonify({"success": False, "error": "key mint failed"}), 500


@orgs_bp.route("/orgs/<slug>/keys", methods=["GET"])
@admin_required
def list_org_keys(slug):
    """Key metadata for a tenant — never the plaintext or hash."""
    pg = get_pg()
    if not pg:
        return _no_pg()
    try:
        cur = pg.cursor()
        cur.execute(
            """SELECT k.id, k.label, k.scopes, k.is_active, k.created_at, k.last_used_at
               FROM api_keys k JOIN tenants t ON t.id = k.tenant_id
               WHERE t.slug = %s ORDER BY k.created_at""",
            (slug,),
        )
        keys = [
            {
                "id": r[0],
                "label": r[1],
                "scopes": r[2],
                "is_active": r[3],
                "created_at": r[4].isoformat() if r[4] else None,
                "last_used_at": r[5].isoformat() if r[5] else None,
            }
            for r in cur.fetchall()
        ]
        pg.close()
        return jsonify({"keys": keys, "count": len(keys)})
    except Exception as e:
        logger.error("list keys failed for %s: %s", slug, e)
        try:
            pg.close()
        except Exception:
            pass
        return jsonify({"success": False, "error": "key list failed"}), 500
