SEVERITY_WEIGHTS = {"info": 0, "warning": 1, "violation": 3, "critical": 5}
CATEGORIES = ["transparency", "fairness", "safety", "privacy", "accountability"]
GRADE_THRESHOLDS = [(95, "A+"), (90, "A"), (85, "B+"), (80, "B"), (70, "C"), (60, "D")]


def calculate_scores(events: list[dict]) -> dict:
    """Score compliance based on violation rate per category.

    Score = 100 * (1 - weighted_violation_rate). A category with all info
    events scores 100. A category where 50% of events are critical scores
    ~50. This scales properly regardless of event volume.
    """
    if not events:
        return {
            "overall": 100.0,
            "grade": "A+",
            "by_category": {c: 100.0 for c in CATEGORIES},
            "event_count": 0,
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

    by_category = {}
    for cat in CATEGORIES:
        if category_max_possible[cat] > 0:
            violation_rate = category_weighted_sum[cat] / category_max_possible[cat]
            score = round(100.0 * (1.0 - violation_rate), 1)
        else:
            score = 100.0
        by_category[cat] = score

    active_categories = [s for c, s in by_category.items() if category_counts.get(c, 0) > 0]
    overall = round(sum(active_categories) / len(active_categories), 1) if active_categories else 100.0

    grade = "F"
    for threshold, g in GRADE_THRESHOLDS:
        if overall >= threshold:
            grade = g
            break

    return {"overall": overall, "grade": grade, "by_category": by_category, "event_count": len(events)}
