from flask import Blueprint, Response, jsonify

from kytran_creed.services.badge_service import generate_badge, VALID_TYPES
from kytran_creed.services.scoring_engine import calculate_scores
from kytran_creed.routes.api_routes import _get_recent_events

badge_bp = Blueprint("badge", __name__, url_prefix="/api/v1")


@badge_bp.route("/badge/<badge_type>")
def get_badge(badge_type):
    # P1.2: global badge = alias for the Institute tenant (None when no PG —
    # unfiltered, same as before).
    from kytran_creed.pg import get_institute_tenant_id

    if badge_type not in VALID_TYPES:
        return jsonify({"error": f"Invalid badge type. Valid: {sorted(VALID_TYPES)}"}), 404
    events = _get_recent_events(30, get_institute_tenant_id())
    scores = calculate_scores(events)
    svg = generate_badge(badge_type, scores)
    return Response(
        svg,
        mimetype="image/svg+xml",
        headers={
            "Cache-Control": "no-cache",
            "Access-Control-Allow-Origin": "*",
        },
    )


@badge_bp.route("/badge/<slug>/<badge_type>")
def get_tenant_badge(slug, badge_type):
    """Per-tenant badge (task #3269 P1.2) — gray PROVISIONAL until the feed
    passes the ADR-004 §5 substance gate."""
    from kytran_creed.pg import get_pg
    from kytran_creed.routes.orgs_routes import _get_public_tenant, _tenant_stats

    if badge_type not in VALID_TYPES:
        return jsonify({"error": f"Invalid badge type. Valid: {sorted(VALID_TYPES)}"}), 404
    pg = get_pg()
    if not pg:
        return jsonify({"error": "multi-tenant mode requires Postgres"}), 503
    try:
        row = _get_public_tenant(pg, slug)
        if not row:
            pg.close()
            return jsonify({"error": "unknown org"}), 404
        tenant_id = str(row[0])
        provisional = _tenant_stats(pg, tenant_id)["provisional"]
        pg.close()
    except Exception:
        try:
            pg.close()
        except Exception:
            pass
        return jsonify({"error": "badge unavailable"}), 500
    scores = calculate_scores(_get_recent_events(30, tenant_id))
    svg = generate_badge(badge_type, scores, provisional=provisional)
    return Response(
        svg,
        mimetype="image/svg+xml",
        headers={
            "Cache-Control": "no-cache",
            "Access-Control-Allow-Origin": "*",
        },
    )


@badge_bp.route("/landing-stats")
def landing_stats():
    """Public endpoint for the landing page stats bar — combines compliance
    scores with live platform agent/dept counts. Cached 5 minutes."""
    from kytran_creed.services.platform_stats import get_platform_stats

    events = _get_recent_events(30)
    scores = calculate_scores(events)

    # Pull live fleet numbers — fail gracefully if platform unreachable
    ps = get_platform_stats() or {}
    agent_total = (ps.get("agents") or {}).get("total", 0)
    dept_count = len((ps.get("welfare") or {}).get("by_department") or [])

    def _fmt_count(n):
        """Format large numbers: 54539 → '54.5K'"""
        if n >= 1_000_000:
            return f"{n/1_000_000:.1f}M"
        if n >= 1_000:
            return f"{n/1_000:.1f}K"
        return str(n)

    return (
        jsonify(
            {
                "grade": scores.get("grade", "A"),
                "overall": round(scores.get("overall", 0), 1),
                "event_count": scores.get("event_count", 0),
                "event_count_fmt": _fmt_count(scores.get("event_count", 0)),
                "agent_count": agent_total,
                "dept_count": dept_count if dept_count else 17,
            }
        ),
        200,
        {
            "Cache-Control": "public, max-age=300",
            "Access-Control-Allow-Origin": "*",
        },
    )
