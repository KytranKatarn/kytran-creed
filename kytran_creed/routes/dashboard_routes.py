import os
import requests
from flask import Blueprint, render_template, jsonify, redirect, url_for
from flask_login import current_user, login_required

from kytran_creed.services.platform_stats import (
    get_platform_stats,
    get_fleet_agents,
    get_ethics_trend,
    get_overflow_activations,
    get_governance_report,
    get_wtf_agents,
)

dashboard_bp = Blueprint("dashboard", __name__)

# Mesh IP — canonical for inter-cluster calls from hub containers (ADR mesh routing)
_PLATFORM_BASE = os.getenv("PLATFORM_BASE_URL", "http://100.64.0.4:3000")
_CREED_API_BASE = f"{_PLATFORM_BASE}/tools/department-hq"


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
    """Public Agent Welfare page — live welfare + ethics governance data."""
    welfare = {}
    try:
        r = requests.get(
            f"{_CREED_API_BASE}/api/creed/public-stats",
            timeout=8,
        )
        if r.status_code == 200:
            welfare = r.json()
    except Exception:
        pass
    trend = get_ethics_trend(30)
    overflow = get_overflow_activations()
    return render_template(
        "welfare.html",
        welfare=welfare,
        trend=trend,
        overflow=overflow,
    )


@dashboard_bp.route("/mood-journal")
def mood_journal():
    """Public Mood Journal — live agent emotional state across the fleet."""
    fleet = get_fleet_agents()
    # Flatten all agents from all nodes into one sorted list
    agents = []
    if fleet and fleet.get("success"):
        for node in fleet.get("nodes", []):
            for ag in node.get("agents", []):
                ag["_node"] = node.get("node_name", "hub")
                agents.append(ag)
    agents.sort(key=lambda a: a.get("stress_level", 0), reverse=True)
    return render_template("mood_journal.html", agents=agents, fleet=fleet)


@dashboard_bp.route("/api/creed/wtf-agents")
def wtf_agents_proxy():
    """Public server-side proxy for WTF News & Media agent stats.

    Filters fleet-agents to department='News & Media' and returns the 6
    WTF agents with live welfare/stress/energy stats.  The mesh URL never
    reaches the browser — this is the only public surface for this data.
    No login required (matches /results public exemption pattern).
    """
    agents = get_wtf_agents()
    return jsonify({"success": True, "agents": agents, "count": len(agents)})


@dashboard_bp.route("/api/ethics/by-department")
def ethics_by_department():
    """JSON endpoint — ethics breakdown grouped by department.

    Proxies through the cached platform stats (5-min TTL) so there is no
    extra network call to the hub.  Returns the ``ethics.by_department``
    list already computed by DHQ ``public-stats``, sorted worst → best.

    Shape of each item::

        {
          "department": str,
          "score": int,        # 0-100
          "grade": str,        # A+…F
          "success_rate": float,
          "high_stress_agents": int,
          "avg_stress": float,
          "welfare_status": str  # green | yellow | red
        }
    """
    stats = get_platform_stats()
    if not stats or not stats.get("success"):
        return jsonify({"success": False, "error": "Platform unreachable", "by_department": []}), 503
    by_dept = (stats.get("ethics") or {}).get("by_department", [])
    return jsonify({"success": True, "by_department": by_dept})


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
