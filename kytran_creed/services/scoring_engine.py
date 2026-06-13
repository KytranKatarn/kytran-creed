import os

SEVERITY_WEIGHTS = {"info": 0, "warning": 1, "violation": 3, "critical": 5}
# The 6 ethics pillars. DO NOT add 'welfare' here — AI-workforce welfare is a
# PARALLEL, distinct metric scored by services/welfare_engine.py from
# category='welfare' events. Welfare must never contribute to the overall ethics
# score. Because only these categories are summed below, a welfare event is
# silently ignored by this scorer even though it is a valid ingest category.
CATEGORIES = ["transparency", "fairness", "safety", "privacy", "accountability", "environmental"]
GRADE_THRESHOLDS = [(95, "A+"), (90, "A"), (85, "B+"), (80, "B"), (70, "C"), (60, "D")]

# Pillar-level minimum-volume gate (#3942): a pillar needs at least this many
# events before its score is statistically meaningful enough to count toward
# the overall. Below the threshold the pillar is reported as provisional and
# excluded — same philosophy as the tenant provisional gate (>=100 events).
PILLAR_MIN_EVENTS = int(os.getenv("CREED_PILLAR_MIN_EVENTS", "100"))


def _grade(score: float) -> str:
    for threshold, g in GRADE_THRESHOLDS:
        if score >= threshold:
            return g
    return "F"


def calculate_scores(events: list[dict]) -> dict:
    """Score compliance based on violation rate per category.

    Score = 100 * (1 - weighted_violation_rate). A category with all info
    events scores 100. A category where 50% of events are critical scores
    ~50. This scales properly regardless of event volume.

    Volume gate: pillars with fewer than PILLAR_MIN_EVENTS events are marked
    ``provisional`` and excluded from the overall when at least one pillar
    qualifies. If NO pillar qualifies (low-volume tenant), the overall falls
    back to all active pillars and is itself flagged ``overall_provisional``
    — a 2-event pillar must neither tank nor inflate a 300k-event overall,
    and a 50-event tenant must not display a confident grade.
    """
    if not events:
        return {
            "overall": 100.0,
            "grade": "A+",
            "by_category": {
                c: {
                    "score": 100.0,
                    "events": 0,
                    "grade": "A+",
                    "provisional": True,
                    "note": "no events recorded",
                }
                for c in CATEGORIES
            },
            "event_count": 0,
            "overall_provisional": True,
            "pillar_min_events": PILLAR_MIN_EVENTS,
            "overall_categories": [],
        }

    category_weighted_sum = {c: 0.0 for c in CATEGORIES}
    category_max_possible = {c: 0.0 for c in CATEGORIES}
    category_counts = {c: 0 for c in CATEGORIES}

    max_weight = max(SEVERITY_WEIGHTS.values())

    for event in events:
        cat = event.get("category", "")
        sev = event.get("severity", "info")
        if cat in category_weighted_sum:
            category_weighted_sum[cat] += SEVERITY_WEIGHTS.get(sev, 0)
            category_max_possible[cat] += max_weight
            category_counts[cat] += 1

    cat_scores = {}
    for cat in CATEGORIES:
        if category_max_possible[cat] > 0:
            violation_rate = category_weighted_sum[cat] / category_max_possible[cat]
            score = round(100.0 * (1.0 - violation_rate), 1)
        else:
            score = 100.0
        cat_scores[cat] = score

    qualified = [c for c in CATEGORIES if category_counts[c] >= PILLAR_MIN_EVENTS]
    active = [c for c in CATEGORIES if category_counts[c] > 0]

    if qualified:
        overall_categories = qualified
        overall_provisional = False
    else:
        # Degenerate case: nothing meets the bar — legacy behavior, flagged.
        overall_categories = active
        overall_provisional = True

    if overall_categories:
        overall = round(sum(cat_scores[c] for c in overall_categories) / len(overall_categories), 1)
    else:
        overall = 100.0

    by_category = {}
    for cat in CATEGORIES:
        entry = {
            "score": cat_scores[cat],
            "events": category_counts[cat],
            "grade": _grade(cat_scores[cat]),
        }
        if cat not in overall_categories:
            entry["provisional"] = True
            if category_counts[cat] == 0:
                entry["note"] = "no events recorded"
            else:
                entry["note"] = (
                    f"insufficient data ({category_counts[cat]} events; "
                    f"minimum {PILLAR_MIN_EVENTS} to count toward overall)"
                )
        elif overall_provisional:
            entry["provisional"] = True
            entry["note"] = (
                f"below minimum volume ({category_counts[cat]} events; "
                f"minimum {PILLAR_MIN_EVENTS} for a non-provisional score)"
            )
        by_category[cat] = entry

    return {
        "overall": overall,
        "grade": _grade(overall),
        "by_category": by_category,
        "event_count": len(events),
        "overall_provisional": overall_provisional,
        "pillar_min_events": PILLAR_MIN_EVENTS,
        "overall_categories": overall_categories,
    }
