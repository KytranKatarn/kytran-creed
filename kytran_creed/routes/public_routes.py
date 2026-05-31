"""Public, read-only C.R.E.E.D. compliance API.

Exposes GET /api/public/score for badge widgets on monitored products
(e.g. what-the-fact.tech/transparency). CORS-open, short-cached, and
protected by a lightweight in-process per-IP token bucket so a single
read-only endpoint does not require Flask-Limiter / Redis.

Note: the token bucket is per-worker. Under a multi-worker gunicorn
deployment the effective limit is RATE_LIMIT * worker_count, which is
acceptable for low-stakes badge traffic.
"""

import logging
import threading
import time
from datetime import datetime, timedelta

try:
    from zoneinfo import ZoneInfo

    _TORONTO = ZoneInfo("America/Toronto")
except Exception:  # pragma: no cover - zoneinfo always present on 3.9+
    _TORONTO = None

from flask import Blueprint, jsonify, request

from kytran_creed.db import get_db
from kytran_creed.pg import get_pg
from kytran_creed.routes.api_routes import _get_recent_events
from kytran_creed.services.scoring_engine import calculate_scores

logger = logging.getLogger(__name__)
public_bp = Blueprint("public", __name__, url_prefix="/api/public")

# --- Lightweight in-process per-IP rate limiting ------------------------------
RATE_LIMIT = 60  # requests
RATE_WINDOW = 60  # seconds
_rate_lock = threading.Lock()
_rate_buckets: dict[str, list[float]] = {}


def _rate_limited(ip: str) -> bool:
    """Return True if this IP has exceeded RATE_LIMIT requests in RATE_WINDOW.

    Simple sliding-window counter keyed by client IP. Trims expired hits on
    every call to keep the dict bounded for active clients.
    """
    now = time.time()
    cutoff = now - RATE_WINDOW
    with _rate_lock:
        hits = [t for t in _rate_buckets.get(ip, []) if t > cutoff]
        if len(hits) >= RATE_LIMIT:
            _rate_buckets[ip] = hits
            return True
        hits.append(now)
        _rate_buckets[ip] = hits
        # Opportunistic cleanup of idle buckets to avoid unbounded growth.
        if len(_rate_buckets) > 4096:
            for k in [k for k, v in _rate_buckets.items() if not v or v[-1] <= cutoff]:
                _rate_buckets.pop(k, None)
        return False


def _count_events_since_midnight() -> int:
    """Count governance events created since local (America/Toronto) midnight.

    Mirrors the PG-first, SQLite-fallback pattern of _get_recent_events.
    """
    now_local = datetime.now(_TORONTO) if _TORONTO else datetime.now()
    midnight_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)

    pg = get_pg()
    if pg:
        try:
            cur = pg.cursor()
            cur.execute(
                "SELECT COUNT(*) FROM governance_events WHERE created_at >= %s",
                (midnight_local,),
            )
            row = cur.fetchone()
            pg.close()
            return int(row[0]) if row else 0
        except Exception as e:
            logger.error("PG count failed, falling back to SQLite: %s", e)
            try:
                pg.close()
            except Exception:
                pass

    # SQLite fallback — stored timestamps are UTC; convert local midnight to UTC.
    if _TORONTO:
        from datetime import timezone

        since = midnight_local.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    else:
        since = midnight_local.strftime("%Y-%m-%d %H:%M:%S")

    conn = get_db()
    try:
        cur = conn.execute(
            "SELECT COUNT(*) AS c FROM governance_events WHERE created_at >= ?",
            (since,),
        )
        row = cur.fetchone()
        return int(row["c"]) if row else 0
    finally:
        conn.close()


@public_bp.route("/score", methods=["GET"])
def public_score():
    """Public read-only compliance summary for badge widgets.

    Returns {score, grade, events_today, active_categories, last_checked}.
    CORS-open with a 60s cache. Per-IP rate limited (60 req/min).
    """
    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "unknown")
    ip = ip.split(",")[0].strip()
    if _rate_limited(ip):
        return (
            jsonify({"error": "rate_limited", "retry_after": RATE_WINDOW}),
            429,
            {
                "Access-Control-Allow-Origin": "*",
                "Retry-After": str(RATE_WINDOW),
            },
        )

    events = _get_recent_events(30)
    scores = calculate_scores(events)

    by_category = scores.get("by_category", {}) or {}
    active_categories = sum(
        1 for v in by_category.values() if isinstance(v, dict) and v.get("events", 0) > 0
    )

    now_local = datetime.now(_TORONTO) if _TORONTO else datetime.now()

    return (
        jsonify(
            {
                "score": round(scores.get("overall", 0), 1),
                "grade": scores.get("grade", "A"),
                "events_today": _count_events_since_midnight(),
                "active_categories": active_categories,
                "last_checked": now_local.isoformat(),
            }
        ),
        200,
        {
            "Cache-Control": "public, max-age=60",
            "Access-Control-Allow-Origin": "*",
        },
    )
