"""Public, read-only AI-workforce WELFARE API (Phase 2, WP-002 §8).

A DISTINCT metric from the 6-pillar ethics score. Reads ONLY
``category='welfare'`` governance events. CORS-open + short-cached, mirroring
the shape/style of /api/v1/scores and /api/v1/badge/*.

Endpoints (all under /api/v1):
  GET /api/v1/welfare                     — institute-tenant welfare summary
  GET /api/v1/orgs/<slug>/welfare         — per-tenant welfare (provisional-gated)
  GET /api/v1/welfare/methodology         — machine-readable WP-002 §8 summary
  GET /api/v1/badge/welfare               — institute welfare SVG grade badge
  GET /api/v1/badge/<slug>/welfare        — per-tenant welfare SVG grade badge

Today (Phase 3 emitter not built) there are zero welfare events, so these
return a clean PROVISIONAL "no welfare data yet" response — never a 500.
"""

import csv
import io
import logging
from datetime import datetime, timedelta

from flask import Blueprint, Response, jsonify, request

from kytran_creed.db import get_db
from kytran_creed.pg import get_pg
from kytran_creed.services.badge_service import BADGE_COLORS
from kytran_creed.services.welfare_engine import (
    WELFARE_METHODOLOGY,
    calculate_welfare,
    grade_for,
)

logger = logging.getLogger(__name__)
welfare_bp = Blueprint("welfare", __name__, url_prefix="/api/v1")

WELFARE_CATEGORY = "welfare"
_CACHE = {"Cache-Control": "public, max-age=60", "Access-Control-Allow-Origin": "*"}


def _fetch_welfare_rows(days: int = 30, tenant_id: str | None = None) -> list:
    """Fetch raw ``category='welfare'`` rows from the last N days.

    Returns a list of row tuples in the SELECT order
    ``(category, severity, event_type, agent_id, metadata, created_at)``.
    PG-first with SQLite fallback, mirroring api_routes._get_recent_events. On
    any error returns ``[]`` (clean PROVISIONAL) — the public endpoints must not
    500 when welfare data is absent or PG is flaky.
    """
    pg = get_pg()
    if pg:
        try:
            sql = (
                "SELECT category, severity, event_type, agent_id, metadata, created_at "
                "FROM governance_events "
                "WHERE category = %s AND created_at >= NOW() - INTERVAL '%s days'"
            )
            params: list = [WELFARE_CATEGORY, days]
            if tenant_id:
                sql += " AND tenant_id = %s"
                params.append(tenant_id)
            cur = pg.cursor()
            cur.execute(sql, params)
            rows = cur.fetchall()
            pg.close()
            return list(rows)
        except Exception as e:
            logger.error("PG welfare fetch failed, falling back to SQLite: %s", e)
            try:
                pg.close()
            except Exception:
                pass

    conn = get_db()
    try:
        since = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
        sql = (
            "SELECT category, severity, event_type, agent_id, metadata, created_at "
            "FROM governance_events WHERE category = ? AND created_at >= ?"
        )
        params = [WELFARE_CATEGORY, since]
        if tenant_id:
            sql += " AND tenant_id = ?"
            params.append(tenant_id)
        cur = conn.execute(sql, params)
        return list(cur.fetchall())
    except Exception as e:
        logger.error("SQLite welfare fetch failed: %s", e)
        return []
    finally:
        conn.close()


def _get_welfare_events(days: int = 30, tenant_id: str | None = None) -> tuple[list[dict], float]:
    """Fetch ``category='welfare'`` events from the last N days for scoring.

    Returns (events, span_days). Thin wrapper over ``_fetch_welfare_rows`` +
    ``_rows_to_events`` so the summary/badge endpoints and the dataset by-day
    fetch share one fetch path. Never raises (delegates the clean-empty
    behavior to ``_fetch_welfare_rows``).
    """
    return _rows_to_events(_fetch_welfare_rows(days, tenant_id), pg_mode=False)


def _rows_to_events(rows, pg_mode: bool) -> tuple[list[dict], float]:
    import json as _json

    events = []
    timestamps = []
    for r in rows:
        # Row order matches the SELECT above for both PG tuples and SQLite Rows.
        category, severity, event_type, agent_id, metadata, created_at = (
            r[0],
            r[1],
            r[2],
            r[3],
            r[4],
            r[5],
        )
        meta = metadata
        if isinstance(meta, str):
            try:
                meta = _json.loads(meta) if meta else {}
            except (ValueError, TypeError):
                meta = {}
        elif meta is None:
            meta = {}
        events.append(
            {
                "category": category,
                "severity": severity,
                "event_type": event_type,
                "agent_id": agent_id,
                "metadata": meta,
            }
        )
        if created_at is not None:
            timestamps.append(created_at)

    span_days = 0.0
    parsed = []
    for ts in timestamps:
        if isinstance(ts, datetime):
            parsed.append(ts)
        else:
            try:
                parsed.append(datetime.fromisoformat(str(ts)))
            except ValueError:
                continue
    if len(parsed) >= 2:
        span_days = (max(parsed) - min(parsed)).total_seconds() / 86400.0
    return events, span_days


@welfare_bp.route("/welfare", methods=["GET"])
def get_welfare():
    """Institute-tenant AI-workforce welfare summary. Alias for the institute
    tenant, exactly like /api/v1/scores. CORS-open, 60s cache."""
    from kytran_creed.pg import get_institute_tenant_id

    days = int(request.args.get("days", 30))
    try:
        events, span = _get_welfare_events(days, get_institute_tenant_id())
        result = calculate_welfare(events, span_days=span)
    except Exception as e:
        logger.error("welfare summary failed: %s", e)
        # Clean provisional response — never 500 on the public surface.
        result = calculate_welfare([], span_days=0.0)
    result["generated_at"] = datetime.utcnow().isoformat() + "Z"
    result["cache_seconds"] = 60
    return jsonify(result), 200, _CACHE


@welfare_bp.route("/orgs/<slug>/welfare", methods=["GET"])
def org_welfare(slug):
    """Per-tenant welfare — same shape as /api/v1/welfare plus tenant context.
    Reuses the public-tenant lookup from orgs_routes. 404 for an unknown org;
    a clean PROVISIONAL body when the tenant has no welfare events yet."""
    from kytran_creed.routes.orgs_routes import _get_public_tenant, _tenant_row_to_dict

    pg = get_pg()
    if not pg:
        return jsonify({"success": False, "error": "multi-tenant mode requires Postgres"}), 503
    try:
        row = _get_public_tenant(pg, slug)
        if not row:
            pg.close()
            return jsonify({"success": False, "error": "unknown org"}), 404
        tenant_id = str(row[0])
        pg.close()
    except Exception as e:
        logger.error("org welfare lookup failed for %s: %s", slug, e)
        try:
            pg.close()
        except Exception:
            pass
        return jsonify({"success": False, "error": "welfare unavailable"}), 500

    days = int(request.args.get("days", 30))
    try:
        events, span = _get_welfare_events(days, tenant_id)
        result = calculate_welfare(events, span_days=span)
    except Exception as e:
        logger.error("org welfare scoring failed for %s: %s", slug, e)
        result = calculate_welfare([], span_days=0.0)
    result["tenant"] = _tenant_row_to_dict(row)
    result["generated_at"] = datetime.utcnow().isoformat() + "Z"
    result["cache_seconds"] = 60
    return jsonify(result), 200, _CACHE


@welfare_bp.route("/welfare/methodology", methods=["GET"])
def welfare_methodology():
    """Machine-readable WP-002 §8 welfare methodology (static structure)."""
    return (
        jsonify(WELFARE_METHODOLOGY),
        200,
        {"Cache-Control": "public, max-age=3600", "Access-Control-Allow-Origin": "*"},
    )


# ── Welfare SVG badge ────────────────────────────────────────────────────────
# Shields-style, mirroring badge_service.BADGE_TEMPLATE but with a WELFARE label
# and provisional-gray when the feed is low-volume. Kept local so the ethics
# badge service stays untouched.
_WELFARE_BADGE = """<svg xmlns="http://www.w3.org/2000/svg" width="210" height="20">
  <linearGradient id="bg" x2="0" y2="100%">
    <stop offset="0" stop-color="#555"/>
    <stop offset="1" stop-color="#333"/>
  </linearGradient>
  <rect rx="3" width="210" height="20" fill="url(#bg)"/>
  <rect rx="3" x="120" width="90" height="20" fill="{color}"/>
  <text x="6" y="14" fill="#fff" font-family="Arial,sans-serif" font-size="11">C.R.E.E.D. Welfare</text>
  <text x="165" y="14" fill="#fff" font-family="Arial,sans-serif" font-size="11" text-anchor="middle">{right}</text>
</svg>"""


def _welfare_badge_svg(result: dict) -> str:
    if result.get("provisional") or result.get("overall") is None:
        return _WELFARE_BADGE.format(color="#6b7280", right="PROVISIONAL")
    grade = result.get("grade", "F")
    score = result.get("overall", 0.0)
    color = BADGE_COLORS.get(grade, "#6b7280")
    return _WELFARE_BADGE.format(color=color, right=f"{grade} ({int(score)}%)")


@welfare_bp.route("/badge/welfare", methods=["GET"])
def welfare_badge():
    """Institute welfare grade badge (SVG). Provisional-gray when low-volume."""
    from kytran_creed.pg import get_institute_tenant_id

    try:
        events, span = _get_welfare_events(30, get_institute_tenant_id())
        result = calculate_welfare(events, span_days=span)
    except Exception as e:
        logger.error("welfare badge failed: %s", e)
        result = calculate_welfare([], span_days=0.0)
    return Response(
        _welfare_badge_svg(result),
        mimetype="image/svg+xml",
        headers={"Cache-Control": "no-cache", "Access-Control-Allow-Origin": "*"},
    )


@welfare_bp.route("/badge/<slug>/welfare", methods=["GET"])
def tenant_welfare_badge(slug):
    """Per-tenant welfare grade badge (SVG)."""
    from kytran_creed.routes.orgs_routes import _get_public_tenant

    pg = get_pg()
    if not pg:
        return jsonify({"error": "multi-tenant mode requires Postgres"}), 503
    try:
        row = _get_public_tenant(pg, slug)
        if not row:
            pg.close()
            return jsonify({"error": "unknown org"}), 404
        tenant_id = str(row[0])
        pg.close()
    except Exception:
        try:
            pg.close()
        except Exception:
            pass
        return jsonify({"error": "badge unavailable"}), 500
    try:
        events, span = _get_welfare_events(30, tenant_id)
        result = calculate_welfare(events, span_days=span)
    except Exception as e:
        logger.error("tenant welfare badge failed for %s: %s", slug, e)
        result = calculate_welfare([], span_days=0.0)
    return Response(
        _welfare_badge_svg(result),
        mimetype="image/svg+xml",
        headers={"Cache-Control": "no-cache", "Access-Control-Allow-Origin": "*"},
    )


# ── #4134 welfare DATASET: history time-series + CSV export ───────────────────
# Grant evidence: a downloadable daily welfare record. Same data, two shapes —
# JSON (/welfare/history) for charts/APIs and CSV (/welfare/export.csv) for
# spreadsheets/grant attachments. Both public, CORS-open, 60s-cached, and
# wrapped to never 500 (clean PROVISIONAL/empty when there is no welfare data).

_DAYS_DEFAULT = 30
_DAYS_MAX = 365
_SEVERITIES = ["info", "warning", "violation", "critical"]

_CSV_COLUMNS = [
    "date",
    "event_count",
    "overall_raw",
    "grade",
    "hours_score",
    "tokens_score",
    "actions_score",
    "stress_score",
    "break_honor_rate",
    "agents_monitored",
    "info",
    "warning",
    "violation",
    "critical",
]


def _parse_days() -> int:
    """``?days=`` clamped to [1, 365]; falls back to the default on bad input."""
    raw = request.args.get("days", _DAYS_DEFAULT)
    try:
        d = int(raw)
    except (TypeError, ValueError):
        return _DAYS_DEFAULT
    return max(1, min(d, _DAYS_MAX))


def _resolve_request_tenant():
    """Resolve which tenant the dataset is for.

    Default (no ``?org=``) = the institute tenant, exactly like /api/v1/welfare.
    ``?org=<slug>`` selects a public tenant (PG-gated, mirrors
    /orgs/<slug>/welfare). Returns ``(tenant_id, error)`` where ``error`` is a
    ready ``(body, status, headers)`` tuple for an invalid/unavailable org,
    else None.
    """
    from kytran_creed.pg import get_institute_tenant_id

    slug = request.args.get("org")
    if not slug:
        return get_institute_tenant_id(), None

    from kytran_creed.routes.orgs_routes import _get_public_tenant

    pg = get_pg()
    if not pg:
        return None, (
            jsonify({"success": False, "error": "multi-tenant mode requires Postgres"}),
            503,
            _CACHE,
        )
    try:
        row = _get_public_tenant(pg, slug)
        if not row:
            pg.close()
            return None, (jsonify({"success": False, "error": "unknown org"}), 404, _CACHE)
        tenant_id = str(row[0])
        pg.close()
        return tenant_id, None
    except Exception as e:
        logger.error("welfare dataset tenant lookup failed for %s: %s", slug, e)
        try:
            pg.close()
        except Exception:
            pass
        return None, (jsonify({"success": False, "error": "tenant unavailable"}), 500, _CACHE)


def _row_date(created_at) -> str | None:
    """UTC ``YYYY-MM-DD`` bucket key for a row timestamp (PG datetime or SQLite
    string). Returns None when the timestamp is missing/unparseable."""
    if created_at is None:
        return None
    if isinstance(created_at, datetime):
        return created_at.strftime("%Y-%m-%d")
    s = str(created_at)
    try:
        return datetime.fromisoformat(s).strftime("%Y-%m-%d")
    except ValueError:
        return s[:10] if len(s) >= 10 else None


def _get_welfare_events_by_day(days: int, tenant_id: str | None = None):
    """Fetch welfare events and bucket them by UTC date.

    Returns ``(daily, all_events, span_days)`` where ``daily`` maps
    ``YYYY-MM-DD`` -> list of event dicts, ``all_events`` is the flat window
    feed (for the totals block) and ``span_days`` is the observed timestamp
    spread (feeds the totals provisional gate). Never raises.
    """
    rows = _fetch_welfare_rows(days, tenant_id)
    # _rows_to_events emits exactly one event per row, in order, so rows and
    # events stay positionally aligned for date bucketing.
    events, span = _rows_to_events(rows, pg_mode=False)
    daily: dict[str, list[dict]] = {}
    for row, event in zip(rows, events):
        date_str = _row_date(row[5])
        if date_str is None:
            continue
        daily.setdefault(date_str, []).append(event)
    return daily, events, span


def _build_welfare_history(days: int, tenant_id: str | None) -> dict:
    """Build the daily welfare series + window totals. Sparse: only days that
    actually have welfare events appear in ``series`` (an empty feed -> [])."""
    try:
        daily, all_events, span = _get_welfare_events_by_day(days, tenant_id)
    except Exception as e:
        logger.error("welfare history build failed: %s", e)
        daily, all_events, span = {}, [], 0.0

    series = []
    for date_str in sorted(daily.keys()):
        day_events = daily[date_str]
        day = calculate_welfare(day_events, span_days=0.0)
        sev_counts = {s: 0 for s in _SEVERITIES}
        for ev in day_events:
            s = ev.get("severity", "info")
            if s in sev_counts:
                sev_counts[s] += 1
        series.append(
            {
                "date": date_str,
                "event_count": day["event_count"],
                "overall_raw": day["overall_raw"],
                "grade": grade_for(day["overall_raw"]),
                "by_dimension": day["by_dimension"],
                "break_honor_rate": day["break_honor_rate"],
                "agents_monitored": day["agents_monitored"],
                "severity_counts": sev_counts,
            }
        )

    return {
        "window_days": days,
        "series": series,
        "totals": calculate_welfare(all_events, span_days=span),
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "cache_seconds": 60,
    }


@welfare_bp.route("/welfare/history", methods=["GET"])
def welfare_history():
    """Daily AI-workforce welfare time-series for grant evidence.

    ``?days=`` (default 30, max 365), optional ``?org=<slug>`` for a specific
    public tenant (default = institute). CORS-open, 60s cache, never 500.
    """
    days = _parse_days()
    tenant_id, error = _resolve_request_tenant()
    if error:
        return error
    return jsonify(_build_welfare_history(days, tenant_id)), 200, _CACHE


def _csv_cell(value):
    """None -> empty cell (so PROVISIONAL/no-data days stay blank, not 'None')."""
    return "" if value is None else value


@welfare_bp.route("/welfare/export.csv", methods=["GET"])
def welfare_export_csv():
    """The /welfare/history dataset as a downloadable CSV (grant attachment).

    Same params as /welfare/history. One row per day with events; an empty feed
    yields a header-only CSV. CORS-open, attachment download.
    """
    days = _parse_days()
    tenant_id, error = _resolve_request_tenant()
    if error:
        return error
    payload = _build_welfare_history(days, tenant_id)

    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(_CSV_COLUMNS)
    for day in payload["series"]:
        bd = day["by_dimension"]
        sc = day["severity_counts"]
        writer.writerow(
            [
                day["date"],
                day["event_count"],
                _csv_cell(day["overall_raw"]),
                day["grade"],
                _csv_cell(bd["hours"]["score"]),
                _csv_cell(bd["tokens"]["score"]),
                _csv_cell(bd["actions"]["score"]),
                _csv_cell(bd["stress"]["score"]),
                _csv_cell(day["break_honor_rate"]),
                day["agents_monitored"],
                sc["info"],
                sc["warning"],
                sc["violation"],
                sc["critical"],
            ]
        )

    slug = request.args.get("org") or "institute"
    filename = f"creed-welfare-{slug}-{days}d.csv"
    return Response(
        out.getvalue(),
        mimetype="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "public, max-age=60",
            "Access-Control-Allow-Origin": "*",
        },
    )
