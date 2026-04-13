SEVERITY_PENALTIES = {"info": 0, "warning": 2, "violation": 10, "critical": 25}
CATEGORIES = ["transparency", "fairness", "safety", "privacy", "accountability"]
GRADE_THRESHOLDS = [(95, "A+"), (90, "A"), (85, "B+"), (80, "B"), (70, "C"), (60, "D")]


def calculate_scores(events: list[dict]) -> dict:
    if not events:
        return {
            "overall": 100.0,
            "grade": "A+",
            "by_category": {c: 100.0 for c in CATEGORIES},
            "event_count": 0,
        }

    category_penalties = {c: 0.0 for c in CATEGORIES}
    category_counts = {c: 0 for c in CATEGORIES}

    for event in events:
        cat = event.get("category", "")
        sev = event.get("severity", "info")
        if cat in category_penalties:
            penalty = SEVERITY_PENALTIES.get(sev, 0)
            category_penalties[cat] += penalty
            category_counts[cat] += 1

    by_category = {}
    for cat in CATEGORIES:
        score = max(0.0, 100.0 - category_penalties[cat])
        by_category[cat] = round(score, 1)

    active_categories = [s for c, s in by_category.items() if category_counts.get(c, 0) > 0]
    overall = round(sum(active_categories) / len(active_categories), 1) if active_categories else 100.0

    grade = "F"
    for threshold, g in GRADE_THRESHOLDS:
        if overall >= threshold:
            grade = g
            break

    return {"overall": overall, "grade": grade, "by_category": by_category, "event_count": len(events)}
