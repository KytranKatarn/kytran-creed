import os
import requests
from flask import Blueprint, render_template, jsonify, redirect, url_for
from flask_login import current_user, login_required

from kytran_creed.services.platform_stats import get_platform_stats

dashboard_bp = Blueprint("dashboard", __name__)

_PLATFORM_BASE = os.getenv("PLATFORM_BASE_URL", "http://192.168.1.200:3000")


@dashboard_bp.route("/")
def index():
    if not current_user.is_authenticated:
        return render_template("landing.html")
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


@dashboard_bp.route("/welfare")
def agent_welfare():
    """Public Agent Welfare page — live welfare data from the platform."""
    welfare = {}
    try:
        r = requests.get(
            f"{_PLATFORM_BASE}/api/creed/public-stats",
            timeout=8,
        )
        if r.status_code == 200:
            welfare = r.json()
    except Exception:
        pass
    return render_template("welfare.html", welfare=welfare)


@dashboard_bp.route("/programs")
def programs():
    return render_template("programs/index.html")


@dashboard_bp.route("/programs/transparency")
def program_transparency():
    return render_template("programs/transparency.html")


@dashboard_bp.route("/programs/welfare")
def program_welfare():
    return render_template("programs/welfare.html")


@dashboard_bp.route("/programs/toolkit")
def program_toolkit():
    return render_template("programs/toolkit.html")
