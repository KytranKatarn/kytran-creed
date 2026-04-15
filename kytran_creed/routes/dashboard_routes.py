from flask import Blueprint, render_template, jsonify
from flask_login import login_required

from kytran_creed.services.platform_stats import get_platform_stats

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/")
@login_required
def index():
    return render_template("dashboard.html")


@dashboard_bp.route("/results")
def public_results():
    return render_template("results.html")


@dashboard_bp.route("/platform")
@login_required
def platform_health():
    stats = get_platform_stats()
    return render_template("platform.html", stats=stats)


@dashboard_bp.route("/api/platform-stats")
@login_required
def platform_stats_api():
    """JSON endpoint for client-side refresh."""
    stats = get_platform_stats()
    if stats:
        return jsonify(stats)
    return jsonify({"success": False, "error": "Platform unreachable"}), 503
