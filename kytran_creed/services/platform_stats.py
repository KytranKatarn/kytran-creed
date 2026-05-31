"""Fetch and cache live governance stats from the A.R.C.H.I.E. platform.

Uses Headscale mesh IP (100.64.0.4) — required for hub-to-hub inter-cluster
calls per canonical architecture (ADR mesh routing mandate, KB #263641).
Never use the public CDN hostname — Hostinger caps at 60s and bypasses queue.
"""

import json
import logging
import time
import urllib.request

logger = logging.getLogger(__name__)

# Mesh IP — canonical for inter-cluster calls from hub containers
_HUB_URL = "http://100.64.0.4:3000/tools/department-hq"

PLATFORM_STATS_URL = f"{_HUB_URL}/api/creed/public-stats"
FLEET_AGENTS_URL = f"{_HUB_URL}/api/creed/fleet-agents"
ETHICS_TREND_URL = f"{_HUB_URL}/api/creed/ethics-trend"
OVERFLOW_ACTIVATIONS_URL = f"{_HUB_URL}/api/creed/overflow-activations"
GOVERNANCE_REPORT_URL = f"{_HUB_URL}/api/creed/governance-report-data"

_stats_cache = {"data": None, "expires": 0}
_fleet_cache = {"data": None, "expires": 0}
_trend_cache: dict = {}  # keyed by days int
_overflow_cache = {"data": None, "expires": 0}


def _fetch_json(url: str, timeout: int = 10):
    """Fetch JSON from url; returns parsed dict or raises."""
    req = urllib.request.Request(url)
    req.add_header("Accept", "application/json")
    resp = urllib.request.urlopen(req, timeout=timeout)
    return json.loads(resp.read())


def get_platform_stats():
    """Return cached platform stats, refreshing every 5 minutes."""
    now = time.time()
    if _stats_cache["data"] and now < _stats_cache["expires"]:
        return _stats_cache["data"]
    try:
        data = _fetch_json(PLATFORM_STATS_URL)
        if data.get("success"):
            _stats_cache["data"] = data
            _stats_cache["expires"] = now + 300  # 5 min TTL
            return data
    except Exception as e:
        logger.warning("Failed to fetch platform stats: %s", e)
    # Return stale data on failure (or None if never fetched)
    return _stats_cache["data"]


def get_fleet_agents():
    """Return cached fleet agent roster across all cluster nodes, refreshing every 60s.

    Returns dict with 'nodes' list grouped by node_name, or None on failure.
    """
    now = time.time()
    if _fleet_cache["data"] and now < _fleet_cache["expires"]:
        return _fleet_cache["data"]
    try:
        data = _fetch_json(FLEET_AGENTS_URL, timeout=8)
        if data.get("success"):
            _fleet_cache["data"] = data
            _fleet_cache["expires"] = now + 60  # 60s TTL
            return data
    except Exception as e:
        logger.warning("Failed to fetch fleet agents: %s", e)
    # Return stale data on failure (or None if never fetched)
    return _fleet_cache["data"]


def get_ethics_trend(days: int = 30):
    """Return ethics trend data for the last N days, cached for 5 min per days value."""
    now = time.time()
    entry = _trend_cache.get(days)
    if entry and now < entry["expires"]:
        return entry["data"]
    try:
        data = _fetch_json(f"{ETHICS_TREND_URL}?days={days}", timeout=10)
        if data.get("success"):
            _trend_cache[days] = {"data": data, "expires": now + 300}
            return data
    except Exception as e:
        logger.warning("Failed to fetch ethics trend (days=%s): %s", days, e)
    return (entry or {}).get("data")


def get_overflow_activations():
    """Return recent overflow activation events, cached for 30s."""
    now = time.time()
    if _overflow_cache["data"] and now < _overflow_cache["expires"]:
        return _overflow_cache["data"]
    try:
        data = _fetch_json(OVERFLOW_ACTIVATIONS_URL, timeout=8)
        if data.get("success"):
            _overflow_cache["data"] = data
            _overflow_cache["expires"] = now + 30
            return data
    except Exception as e:
        logger.warning("Failed to fetch overflow activations: %s", e)
    return _overflow_cache["data"]


_wtf_agents_cache = {"data": None, "expires": 0}


def get_wtf_agents():
    """Return the 6 WTF News & Media agents with live welfare stats.

    Reuses the existing fleet-agents fetch (60s TTL cache) and filters to
    department == 'News & Media'.  Returns a list of agent dicts; empty list
    on failure.  The mesh URL never leaves the server — callers proxy this
    via /api/creed/wtf-agents.
    """
    now = time.time()
    if _wtf_agents_cache["data"] is not None and now < _wtf_agents_cache["expires"]:
        return _wtf_agents_cache["data"]

    fleet = get_fleet_agents()
    agents = []
    seen = set()
    if fleet and fleet.get("success"):
        for node in fleet.get("nodes", []):
            for ag in node.get("agents", []):
                if (ag.get("department") or "").strip() != "News & Media":
                    continue
                # fleet-agents lists each agent once per node it is stationed
                # on; dedup by id (fallback name) so each News & Media agent
                # renders a single card on the Results page.
                key = ag.get("id") or ag.get("name")
                if key in seen:
                    continue
                seen.add(key)
                agents.append(
                    {
                        "name": ag.get("name", ""),
                        "display_name": ag.get("display_name") or ag.get("name", ""),
                        "department": ag.get("department", "News & Media"),
                        "shift_state": ag.get("shift_state", "unknown"),
                        "stress_level": ag.get("stress_level", 0),
                        "energy_level": ag.get("energy_level", 0),
                        "welfare_score": ag.get("welfare_score", 0),
                        "tasks_completed_today": ag.get("tasks_completed_today", 0),
                        "current_mood": ag.get("current_mood", "neutral"),
                        "in_rest": bool(ag.get("in_rest")),
                    }
                )

    _wtf_agents_cache["data"] = agents
    _wtf_agents_cache["expires"] = now + 60  # 60s TTL matches fleet cache
    return agents


def get_governance_report(quarter: str = ""):
    """Return governance report JSON for the given quarter (or latest if blank).

    Not cached — quarterly reports are infrequent and always from DB.
    """
    url = GOVERNANCE_REPORT_URL
    if quarter:
        url = f"{url}?quarter={quarter}"
    try:
        return _fetch_json(url, timeout=10)
    except Exception as e:
        logger.warning("Failed to fetch governance report (quarter=%r): %s", quarter, e)
    return None
