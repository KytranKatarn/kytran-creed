from flask import Blueprint, Response, jsonify

from kytran_creed.services.badge_service import generate_badge, VALID_TYPES
from kytran_creed.services.scoring_engine import calculate_scores
from kytran_creed.routes.api_routes import _get_recent_events

badge_bp = Blueprint("badge", __name__, url_prefix="/api/v1")


@badge_bp.route("/badge/<badge_type>")
def get_badge(badge_type):
    if badge_type not in VALID_TYPES:
        return jsonify({"error": f"Invalid badge type. Valid: {sorted(VALID_TYPES)}"}), 404
    events = _get_recent_events(30)
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
