"""Internal tenant-admin API for the hub's C.R.E.E.D. Command module (#3945).

Server-to-server (X-Internal-Key) read surface so E.T.H.O.S.'s workspace on the
platform can show + manage tenants without a browser session. The mutating
actions (approve/reject/mint-key) reuse the existing onboarding/orgs endpoints,
which now accept the same internal key via @internal_or_admin.

All endpoints here are admin-or-internal only and are NEVER part of the public
CORS surface.
"""

import logging

from flask import Blueprint, jsonify

from kytran_creed.auth import internal_or_admin
from kytran_creed.pg import get_pg
from kytran_creed.routes.orgs_routes import _tenant_stats
from kytran_creed.services.scoring_engine import calculate_scores

logger = logging.getLogger(__name__)
internal_bp = Blueprint("internal", __name__, url_prefix="/api/internal")


def _recent_events_for(pg, tenant_id, days=30):
    cur = pg.cursor()
    cur.execute(
        """SELECT category, severity FROM governance_events
           WHERE tenant_id = %s AND created_at >= NOW() - (%s || ' days')::interval""",
        (tenant_id, days),
    )
    return [{"category": r[0], "severity": r[1]} for r in cur.fetchall()]


@internal_bp.route("/tenants", methods=["GET"])
@internal_or_admin
def internal_tenants():
    """Every tenant (pending/active/suspended) with score + freshness for the
    active ones — the data the Command Center Tenants panel renders."""
    pg = get_pg()
    if not pg:
        return jsonify({"success": False, "error": "multi-tenant mode requires Postgres"}), 503
    try:
        cur = pg.cursor()
        cur.execute(
            """SELECT id, slug, name, website, country, status, listing,
                      verification_tier, contact_email, created_at
               FROM tenants ORDER BY created_at"""
        )
        rows = cur.fetchall()
        tenants = []
        for r in rows:
            tid, slug, name, website, country, status, listing, vtier, email, created = r
            item = {
                "slug": slug,
                "name": name,
                "website": website,
                "country": country,
                "status": status,
                "listing": listing,
                "verification_tier": vtier,
                "contact_email": email,
                "member_since": created.isoformat() if created else None,
                "overall": None,
                "grade": None,
                "provisional": None,
                "events_30d": None,
                "last_event_at": None,
            }
            if status == "active":
                try:
                    stats = _tenant_stats(pg, str(tid))
                    scores = calculate_scores(_recent_events_for(pg, str(tid)))
                    item["overall"] = round(scores.get("overall", 0), 1)
                    item["grade"] = "PROVISIONAL" if stats["provisional"] else scores.get("grade")
                    item["provisional"] = stats["provisional"]
                    item["events_30d"] = stats["events_30d"]
                    item["last_event_at"] = stats["last_event_at"]
                except Exception as e:
                    logger.warning("score calc failed for %s: %s", slug, e)
            tenants.append(item)
        pg.close()
        counts = {
            "total": len(tenants),
            "pending": sum(1 for t in tenants if t["status"] == "pending"),
            "active": sum(1 for t in tenants if t["status"] == "active"),
            "suspended": sum(1 for t in tenants if t["status"] == "suspended"),
        }
        return jsonify({"success": True, "tenants": tenants, "counts": counts})
    except Exception as e:
        logger.error("internal_tenants failed: %s", e)
        try:
            pg.close()
        except Exception:
            pass
        return jsonify({"success": False, "error": "tenant list unavailable"}), 500


@internal_bp.route("/applications", methods=["GET"])
@internal_or_admin
def internal_applications():
    """Pending onboarding applications awaiting approve/reject."""
    pg = get_pg()
    if not pg:
        return jsonify({"success": False, "error": "multi-tenant mode requires Postgres"}), 503
    try:
        cur = pg.cursor()
        cur.execute(
            """SELECT slug, name, website, country, contact_email, email_verified,
                      ai_description, created_at
               FROM tenants WHERE status = 'pending' ORDER BY created_at"""
        )
        apps = [
            {
                "slug": r[0],
                "name": r[1],
                "website": r[2],
                "country": r[3],
                "contact_email": r[4],
                "email_verified": bool(r[5]),
                "ai_description": r[6],
                "applied_at": r[7].isoformat() if r[7] else None,
            }
            for r in cur.fetchall()
        ]
        pg.close()
        return jsonify({"success": True, "applications": apps, "count": len(apps)})
    except Exception as e:
        logger.error("internal_applications failed: %s", e)
        try:
            pg.close()
        except Exception:
            pass
        return jsonify({"success": False, "error": "applications unavailable"}), 500
