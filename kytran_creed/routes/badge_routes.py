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
    return Response(svg, mimetype="image/svg+xml", headers={"Cache-Control": "no-cache"})
