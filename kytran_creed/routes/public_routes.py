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
import re
import threading
import time
import uuid
from collections import defaultdict, deque
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


@public_bp.route("/remediations", methods=["GET"])
def public_remediations():
    """Public read-only Remediation Registry payload.

    Returns the curated registry of known product limitations + governance
    position (see kytran_creed/remediation_data.py). CORS-open, 5-min cache,
    per-IP rate limited. Consumed by product "Known Limitations" sections and
    by creed-ai.org. Static content — no DB read.
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

    from kytran_creed.remediation_data import to_public_dict

    return (
        jsonify(to_public_dict()),
        200,
        {
            "Cache-Control": "public, max-age=300",
            "Access-Control-Allow-Origin": "*",
        },
    )


@public_bp.route("/oversight", methods=["GET"])
def public_oversight():
    """Public read-only Human Oversight Registry payload (task #3264).

    Returns the curated human-in-the-loop framework — which AI decisions are
    autonomous vs require human approval, by risk level (see
    kytran_creed/oversight_data.py). CORS-open, 5-min cache, per-IP rate
    limited. Static content — no DB read.
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

    from kytran_creed.oversight_data import to_public_dict

    return (
        jsonify(to_public_dict()),
        200,
        {
            "Cache-Control": "public, max-age=300",
            "Access-Control-Allow-Origin": "*",
        },
    )


# --- Redress requests (accountability.html) -----------------------------------
_EMAIL_RE = re.compile(r"^[\w.+-]+@[\w-]+\.[\w.-]{2,}$")
_REASON_MAX_LEN = 5000

# Filing abuse guard: separate, stricter bucket than the read endpoints — a
# redress request is a serious human-reviewed submission, not badge traffic.
REDRESS_RATE_LIMIT = 5
REDRESS_RATE_WINDOW = 3600
_redress_hits: dict[str, deque] = defaultdict(deque)


def _redress_rate_limited(ip: str) -> bool:
    now = time.time()
    hits = _redress_hits[ip]
    while hits and hits[0] < now - REDRESS_RATE_WINDOW:
        hits.popleft()
    if len(hits) >= REDRESS_RATE_LIMIT:
        return True
    hits.append(now)
    return False


@public_bp.route("/accountability", methods=["GET"])
def public_accountability():
    """Public read-only redress-request stats for accountability.html.

    Returns {total, by_status, avg_resolution_days, sla_business_days,
    resolution_is_human}. CORS-open, 60s cache, per-IP rate limited.
    """
    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "unknown")
    ip = ip.split(",")[0].strip()
    if _rate_limited(ip):
        return (
            jsonify({"error": "rate_limited", "retry_after": RATE_WINDOW}),
            429,
            {"Access-Control-Allow-Origin": "*", "Retry-After": str(RATE_WINDOW)},
        )

    from kytran_creed.redress_store import get_redress_stats

    try:
        stats = get_redress_stats()
    except Exception as e:
        logger.error("public_accountability failed: %s", e)
        stats = {
            "total": 0,
            "by_status": {"pending": 0, "under_review": 0, "resolved": 0, "denied": 0},
            "avg_resolution_days": None,
            "sla_business_days": 5,
            "resolution_is_human": True,
        }

    return (
        jsonify(stats),
        200,
        {"Cache-Control": "public, max-age=60", "Access-Control-Allow-Origin": "*"},
    )


@public_bp.route("/redress-request", methods=["POST"])
def public_redress_request():
    """File a redress request contesting an AI-driven decision.

    Body: {reason (required), ai_decision_ref, desired_outcome, email}.
    Returns {request_ref, sla_due_at} on success. Never auto-resolves — a
    human reviewer works the queue. CORS-open, strictly rate limited (5/hr/IP).
    """
    data = request.get_json(silent=True) or {}
    reason = (data.get("reason") or "").strip()
    ai_decision_ref = (data.get("ai_decision_ref") or "").strip()[:200]
    desired_outcome = (data.get("desired_outcome") or "").strip()
    email = (data.get("email") or "").strip()

    # Validate BEFORE consuming rate-limit budget — a user who fumbles the
    # form (blank reason, typo'd email) shouldn't burn their 5/hr allowance
    # before they can submit a real request.
    if not reason:
        return (
            jsonify({"error": "Please describe why you are contesting the decision."}),
            400,
            {"Access-Control-Allow-Origin": "*"},
        )
    if len(reason) > _REASON_MAX_LEN:
        reason = reason[:_REASON_MAX_LEN]
    if email and not _EMAIL_RE.match(email):
        return (
            jsonify({"error": "Please provide a valid email address, or leave it blank."}),
            400,
            {"Access-Control-Allow-Origin": "*"},
        )

    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "unknown")
    ip = ip.split(",")[0].strip()
    if _redress_rate_limited(ip):
        return (
            jsonify({"error": "rate_limited", "retry_after": REDRESS_RATE_WINDOW}),
            429,
            {"Access-Control-Allow-Origin": "*", "Retry-After": str(REDRESS_RATE_WINDOW)},
        )

    from kytran_creed.redress_store import store_redress_request

    request_ref = "RR-" + uuid.uuid4().hex[:8].upper()
    try:
        row_id, sla_due_at = store_redress_request(
            request_ref, reason, ai_decision_ref, desired_outcome, email
        )
    except Exception as e:
        logger.error("public_redress_request store failed: %s", e)
        row_id, sla_due_at = None, None

    if row_id is None:
        return (
            jsonify({"error": "Could not submit — please try again."}),
            502,
            {"Access-Control-Allow-Origin": "*"},
        )

    return (
        jsonify({"request_ref": request_ref, "sla_due_at": sla_due_at.isoformat() + "Z"}),
        201,
        {"Access-Control-Allow-Origin": "*"},
    )


@public_bp.route("/incidents", methods=["GET"])
def public_incidents():
    """Public AI incident disclosure log (task #3263).

    Returns only DISCLOSED incidents (status.io-style) — filing an incident does
    not auto-publish it. CORS-open, 60s cache, per-IP rate limited.
    """
    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "unknown")
    ip = ip.split(",")[0].strip()
    if _rate_limited(ip):
        return (
            jsonify({"error": "rate_limited", "retry_after": RATE_WINDOW}),
            429,
            {"Access-Control-Allow-Origin": "*", "Retry-After": str(RATE_WINDOW)},
        )

    from kytran_creed.incident_store import list_incidents

    try:
        incidents = list_incidents(disclosed_only=True)
    except Exception as e:
        logger.error("public_incidents failed: %s", e)
        incidents = []

    return (
        jsonify(
            {
                "registry": "C.R.E.E.D. AI Incident Disclosure Log",
                "count": len(incidents),
                "incidents": incidents,
            }
        ),
        200,
        {
            "Cache-Control": "public, max-age=60",
            "Access-Control-Allow-Origin": "*",
        },
    )
