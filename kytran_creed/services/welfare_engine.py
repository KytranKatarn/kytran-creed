"""AI-workforce welfare scorer — a DISTINCT public metric (Phase 2, WP-002 §8).

This is a SEPARATE scorer from the 6-pillar ethics engine in
``scoring_engine.py``. It scores how well an AI workforce is *treated* — the
hours/tokens/actions/stress load placed on agents and whether scheduled rest
("breaks") is honored — NOT the ethics of the AI's outputs.

It reads ONLY governance events where ``category == 'welfare'`` (a category the
hub emits starting in Phase 3). Welfare events never touch the ethics pillars:
``scoring_engine.CATEGORIES`` does not include ``'welfare'``, so a welfare event
is simply ignored by the ethics scorer.

Statistical style mirrors the ethics scorer: a weighted violation rate over a
30-day rolling window. A welfare *dimension* with all-``info`` events scores
100; a dimension where half its events are ``critical`` scores ~50. The same
provisional gate (min events / min dimensions / min span days) keeps a
low-volume tenant from displaying a fake-confident grade.

Welfare event convention (what the Phase 3 emitter posts):

    {
      "category": "welfare",
      "event_type": "welfare_hours" | "welfare_tokens" | "welfare_actions"
                    | "welfare_stress" | "welfare_break_honored"
                    | "welfare_break_violated",
      "severity": "info" | "warning" | "violation" | "critical",
      "metadata": { "dimension": "hours|tokens|actions|stress", ... }
    }

The ``dimension`` is resolved from ``metadata.dimension`` first, then from the
``event_type`` prefix, so the emitter can use either convention. Break-honor
events (``welfare_break_honored`` / ``welfare_break_violated``) feed the
``break_honor_rate`` and also map to the ``actions`` dimension by default.
"""

import os

# Same governance severity ladder as the ethics scorer — a welfare "violation"
# (e.g. an agent pushed past its token budget) weighs the same as an ethics one.
SEVERITY_WEIGHTS = {"info": 0, "warning": 1, "violation": 3, "critical": 5}

# The four welfare dimensions. These are NOT ethics pillars — they describe
# workload pressure on the AI workforce.
DIMENSIONS = ["hours", "tokens", "actions", "stress"]

GRADE_THRESHOLDS = [(95, "A+"), (90, "A"), (85, "B+"), (80, "B"), (70, "C"), (60, "D")]

# Provisional gate — mirrors orgs_routes PROVISIONAL_* and scoring_engine's
# philosophy: no confident welfare grade until the feed has substance. Tunable
# via env so the hub can dial them without a redeploy (defaults match the
# ethics tenant gate so the two metrics behave consistently).
WELFARE_MIN_EVENTS = int(os.getenv("CREED_WELFARE_MIN_EVENTS", "100"))
WELFARE_MIN_DIMENSIONS = int(os.getenv("CREED_WELFARE_MIN_DIMENSIONS", "3"))
WELFARE_MIN_SPAN_DAYS = int(os.getenv("CREED_WELFARE_MIN_SPAN_DAYS", "14"))

# EWMA smoothing factor for the headline welfare score, applied over the
# per-event sequence so a single spike does not whip the public grade. Higher =
# more responsive. Mirrors the hub's D3 EWMA-smoothed welfare headline (PR #1665).
WELFARE_EWMA_ALPHA = float(os.getenv("CREED_WELFARE_EWMA_ALPHA", "0.3"))

# event_type -> dimension fallback (used when metadata.dimension is absent).
_EVENT_TYPE_DIMENSION = {
    "welfare_hours": "hours",
    "welfare_tokens": "tokens",
    "welfare_actions": "actions",
    "welfare_stress": "stress",
    "welfare_break_honored": "actions",
    "welfare_break_violated": "actions",
}

_BREAK_HONORED_TYPES = {"welfare_break_honored", "break_honored"}
_BREAK_VIOLATED_TYPES = {"welfare_break_violated", "break_violated", "break_skipped"}


def _grade(score: float) -> str:
    for threshold, g in GRADE_THRESHOLDS:
        if score >= threshold:
            return g
    return "F"


def grade_for(score: float | None) -> str:
    """Public grade mapper: numeric score -> letter band; PROVISIONAL when None.

    Lets callers (e.g. the welfare history/CSV dataset) grade a raw per-day
    score without reaching into the private ``_grade``. A ``None`` score (a day
    or window with no scorable events) is PROVISIONAL, never a fake 'F'.
    """
    if score is None:
        return "PROVISIONAL"
    return _grade(score)


def _resolve_dimension(event: dict) -> str | None:
    """Map a welfare event to one of the four dimensions.

    metadata.dimension wins; otherwise fall back to the event_type prefix. An
    unrecognized event still counts toward overall via a catch-all but is not
    attributed to a dimension (returns None) so the by_dimension breakdown stays
    clean.
    """
    meta = event.get("metadata") or {}
    if isinstance(meta, dict):
        dim = meta.get("dimension")
        if isinstance(dim, str) and dim.strip().lower() in DIMENSIONS:
            return dim.strip().lower()
    etype = (event.get("event_type") or "").strip().lower()
    if etype in _EVENT_TYPE_DIMENSION:
        return _EVENT_TYPE_DIMENSION[etype]
    # Loose prefix match: "welfare_tokens_over" -> tokens.
    for dim in DIMENSIONS:
        if etype.startswith(f"welfare_{dim}") or etype == dim:
            return dim
    return None


def _empty_result(reason: str) -> dict:
    """Clean 'no welfare data yet' response — NEVER a 500. Expected today while
    the Phase 3 emitter does not yet exist."""
    return {
        "overall": None,
        "grade": "PROVISIONAL",
        "ewma_score": None,
        "by_dimension": {
            d: {
                "score": None,
                "grade": "PROVISIONAL",
                "events": 0,
                "provisional": True,
                "note": "no welfare data yet",
            }
            for d in DIMENSIONS
        },
        "break_honor_rate": None,
        "agents_monitored": 0,
        "event_count": 0,
        "provisional": True,
        "provisional_reason": reason,
        "gate": {
            "min_events": WELFARE_MIN_EVENTS,
            "min_dimensions": WELFARE_MIN_DIMENSIONS,
            "min_span_days": WELFARE_MIN_SPAN_DAYS,
        },
    }


def calculate_welfare(events: list[dict], span_days: float | None = None) -> dict:
    """Score AI-workforce welfare from ``category='welfare'`` events.

    ``events`` rows should carry at least ``severity`` + ``event_type`` and
    optionally ``metadata`` (dict), ``agent_id``. ``span_days`` is the observed
    spread of the event timestamps (caller-computed); when None it is treated as
    0 which keeps a single-burst feed provisional.

    Returns a dict with the public welfare shape. When there are no welfare
    events the dimensions report ``provisional`` with score ``None`` — a clean
    "no data yet" response, never an error.
    """
    if not events:
        return _empty_result("no welfare events recorded")

    dim_weighted_sum = {d: 0.0 for d in DIMENSIONS}
    dim_max_possible = {d: 0.0 for d in DIMENSIONS}
    dim_counts = {d: 0 for d in DIMENSIONS}

    max_weight = max(SEVERITY_WEIGHTS.values())

    # Overall is computed across ALL welfare events (attributed or not) so a
    # mis-tagged event still pulls the headline; EWMA smooths the sequence.
    overall_weighted_sum = 0.0
    overall_max_possible = 0.0
    ewma = None
    agents = set()
    breaks_honored = 0
    breaks_total = 0

    for event in events:
        sev = event.get("severity", "info")
        w = SEVERITY_WEIGHTS.get(sev, 0)

        overall_weighted_sum += w
        overall_max_possible += max_weight
        # Per-event "score" then EWMA-fold for the smoothed headline.
        ev_score = 100.0 * (1.0 - (w / max_weight)) if max_weight else 100.0
        ewma = ev_score if ewma is None else (WELFARE_EWMA_ALPHA * ev_score + (1 - WELFARE_EWMA_ALPHA) * ewma)

        aid = event.get("agent_id")
        if aid:
            agents.add(aid)

        etype = (event.get("event_type") or "").strip().lower()
        if etype in _BREAK_HONORED_TYPES:
            breaks_honored += 1
            breaks_total += 1
        elif etype in _BREAK_VIOLATED_TYPES:
            breaks_total += 1

        dim = _resolve_dimension(event)
        if dim in dim_weighted_sum:
            dim_weighted_sum[dim] += w
            dim_max_possible[dim] += max_weight
            dim_counts[dim] += 1

    dim_scores = {}
    for d in DIMENSIONS:
        if dim_max_possible[d] > 0:
            rate = dim_weighted_sum[d] / dim_max_possible[d]
            dim_scores[d] = round(100.0 * (1.0 - rate), 1)
        else:
            dim_scores[d] = None  # no data for this dimension yet

    if overall_max_possible > 0:
        overall = round(100.0 * (1.0 - overall_weighted_sum / overall_max_possible), 1)
    else:
        overall = 100.0

    ewma_score = round(ewma, 1) if ewma is not None else None

    # Provisional gate — same three-factor substance test as the ethics tenant
    # gate, applied to welfare-specific volume.
    active_dims = sum(1 for d in DIMENSIONS if dim_counts[d] > 0)
    total = len(events)
    span = float(span_days or 0)
    provisional = not (
        total >= WELFARE_MIN_EVENTS
        and active_dims >= WELFARE_MIN_DIMENSIONS
        and span >= WELFARE_MIN_SPAN_DAYS
    )

    by_dimension = {}
    for d in DIMENSIONS:
        score = dim_scores[d]
        entry = {
            "score": score,
            "grade": _grade(score) if score is not None else "PROVISIONAL",
            "events": dim_counts[d],
        }
        if dim_counts[d] == 0:
            entry["provisional"] = True
            entry["note"] = "no welfare data yet"
        elif provisional:
            entry["provisional"] = True
            entry["note"] = (
                f"below minimum volume ({dim_counts[d]} events; "
                f"feed-level gate {WELFARE_MIN_EVENTS} events / "
                f"{WELFARE_MIN_DIMENSIONS} dimensions / {WELFARE_MIN_SPAN_DAYS}d)"
            )
        by_dimension[d] = entry

    break_honor_rate = round(breaks_honored / breaks_total, 3) if breaks_total > 0 else None

    return {
        "overall": None if provisional else overall,
        "grade": "PROVISIONAL" if provisional else _grade(overall),
        # Raw (un-gated) overall is still surfaced for transparency, like the
        # ethics scorer keeps raw pillar scores visible while provisional.
        "overall_raw": overall,
        "ewma_score": ewma_score,
        "by_dimension": by_dimension,
        "break_honor_rate": break_honor_rate,
        "agents_monitored": len(agents),
        "event_count": total,
        "span_days": round(span, 1),
        "provisional": provisional,
        "gate": {
            "min_events": WELFARE_MIN_EVENTS,
            "min_dimensions": WELFARE_MIN_DIMENSIONS,
            "min_span_days": WELFARE_MIN_SPAN_DAYS,
        },
    }


# ── Machine-readable methodology (WP-002 §8) ─────────────────────────────────
# Structure is real + stable; prose is a stub the public site/whitepaper expands.
# Per-LLM token budgets mirror the hub welfare engine (KB #270628) — the daily
# token ceilings the hub recalibrates weekly (p90 × 1.3, floor 50k).

WELFARE_METHODOLOGY = {
    "standard": "C.R.E.E.D. WP-002",
    "section": "§8 AI-Workforce Welfare",
    "version": "1",
    "summary": (
        "Welfare is a DISTINCT public metric, separate from the 6-pillar ethics "
        "score. It grades how an AI workforce is treated — workload pressure "
        "across four dimensions and whether scheduled rest is honored — on a "
        "30-day rolling window using a weighted violation-rate model identical "
        "in statistical style to the ethics scorer."
    ),
    "scope": "Treatment of the AI workforce (workload, rest), NOT the ethics of AI outputs.",
    "dimensions": [
        {
            "key": "hours",
            "label": "Duty Hours",
            "describes": "Wall-clock on-duty time per agent vs its rest cadence.",
        },
        {
            "key": "tokens",
            "label": "Token Load",
            "describes": "Daily token consumption vs the agent's per-model token budget.",
        },
        {
            "key": "actions",
            "label": "Action Volume",
            "describes": "Task/action count vs sustainable throughput, incl. break honoring.",
        },
        {
            "key": "stress",
            "label": "Stress / Fatigue",
            "describes": "Modeled stress + energy state from the load engine.",
        },
    ],
    "severity_weights": SEVERITY_WEIGHTS,
    "scoring": {
        "model": "score = 100 * (1 - weighted_violation_rate)",
        "window_days": 30,
        "ewma_alpha": WELFARE_EWMA_ALPHA,
        "ewma_note": "Headline welfare score is EWMA-smoothed so a single spike does not whip the public grade.",
    },
    "grading_bands": [{"min": t, "grade": g} for t, g in GRADE_THRESHOLDS] + [{"min": 0, "grade": "F"}],
    "provisional_gate": {
        "min_events": WELFARE_MIN_EVENTS,
        "min_dimensions": WELFARE_MIN_DIMENSIONS,
        "min_span_days": WELFARE_MIN_SPAN_DAYS,
        "note": (
            "Below any threshold the welfare grade is PROVISIONAL (no confident "
            "grade for a low-volume feed) — same philosophy as the ethics gate."
        ),
    },
    "token_budgets": {
        "model": "per-LLM daily token ceiling",
        "recalibration": "weekly: token_limit_per_day = max(50000, p90(30d daily tokens) * 1.3)",
        "ceiling": "clamped to base * 2 per model so a runaway day cannot inflate the budget",
        "note": (
            "Token-load welfare compares each agent's 24h-rolling token use to "
            "its budget; sustained over-budget use emits a welfare violation."
        ),
    },
    "break_honoring": {
        "describes": "Share of scheduled rest/break cycles the workforce actually took.",
        "honored_event_types": sorted(_BREAK_HONORED_TYPES),
        "violated_event_types": sorted(_BREAK_VIOLATED_TYPES),
    },
    "event_convention": {
        "category": "welfare",
        "event_types": sorted(set(_EVENT_TYPE_DIMENSION) | _BREAK_HONORED_TYPES | _BREAK_VIOLATED_TYPES),
        "dimension_resolution": "metadata.dimension first, then event_type prefix",
    },
    "separation_guarantee": (
        "category='welfare' events are excluded from the ethics CATEGORIES, so "
        "welfare can never contribute to the transparency/fairness/safety/"
        "privacy/accountability/environmental pillars or the overall ethics grade."
    ),
}
