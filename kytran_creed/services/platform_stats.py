"""Fetch and cache live governance stats from the A.R.C.H.I.E. platform."""

import json
import logging
import time
import urllib.request

logger = logging.getLogger(__name__)

PLATFORM_STATS_URL = (
    "http://192.168.1.200:3000/tools/department-hq/api/creed/public-stats"
)

_stats_cache = {"data": None, "expires": 0}


def get_platform_stats():
    """Return cached platform stats, refreshing every 5 minutes."""
    now = time.time()
    if _stats_cache["data"] and now < _stats_cache["expires"]:
        return _stats_cache["data"]
    try:
        req = urllib.request.Request(PLATFORM_STATS_URL)
        req.add_header("Accept", "application/json")
        resp = urllib.request.urlopen(req, timeout=10)
        raw = resp.read()
        data = json.loads(raw)
        if data.get("success"):
            _stats_cache["data"] = data
            _stats_cache["expires"] = now + 300  # 5 min TTL
            return data
    except Exception as e:
        logger.warning("Failed to fetch platform stats: %s", e)
    # Return stale data on failure (or None if never fetched)
    return _stats_cache["data"]
