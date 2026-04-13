from kytran_creed.services.scoring_engine import calculate_scores


def test_perfect_score_with_no_violations():
    events = [
        {"category": "transparency", "severity": "info"},
        {"category": "safety", "severity": "info"},
        {"category": "fairness", "severity": "info"},
    ]
    scores = calculate_scores(events)
    assert scores["overall"] >= 95.0
    assert "transparency" in scores["by_category"]


def test_violations_reduce_score():
    events = [
        {"category": "safety", "severity": "info"},
        {"category": "safety", "severity": "violation"},
        {"category": "safety", "severity": "critical"},
    ]
    scores = calculate_scores(events)
    assert scores["by_category"]["safety"] < 80.0


def test_empty_events_returns_baseline():
    scores = calculate_scores([])
    assert scores["overall"] == 100.0


def test_grade_assignment():
    events = [{"category": "transparency", "severity": "info"}] * 20
    scores = calculate_scores(events)
    assert scores["grade"] in ("A+", "A", "B+", "B", "C", "D", "F")
