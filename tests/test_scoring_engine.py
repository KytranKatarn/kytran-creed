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
    # by_category values are dicts ({score, grade, events}) since the public
    # scores API expansion — this test predated that shape change
    assert scores["by_category"]["safety"]["score"] < 80.0


def test_empty_events_returns_baseline():
    scores = calculate_scores([])
    assert scores["overall"] == 100.0


def test_grade_assignment():
    events = [{"category": "transparency", "severity": "info"}] * 20
    scores = calculate_scores(events)
    assert scores["grade"] in ("A+", "A", "B+", "B", "C", "D", "F")


# --- Pillar minimum-volume gate (#3942) ---


def test_low_volume_pillar_excluded_when_others_qualify():
    """A 2-event pillar must not tank an overall built on high-volume pillars."""
    events = [{"category": "transparency", "severity": "info"}] * 120 + [
        {"category": "environmental", "severity": "critical"},
        {"category": "environmental", "severity": "critical"},
    ]
    scores = calculate_scores(events)
    assert scores["overall"] == 100.0
    assert scores["grade"] == "A+"
    assert scores["overall_provisional"] is False
    assert scores["overall_categories"] == ["transparency"]
    env = scores["by_category"]["environmental"]
    assert env["provisional"] is True
    assert "insufficient data" in env["note"]
    assert env["events"] == 2
    assert env["score"] == 0.0  # raw score still reported honestly
    assert "provisional" not in scores["by_category"]["transparency"]


def test_all_low_volume_falls_back_to_legacy_overall():
    """No pillar qualifies -> legacy averaging, flagged overall_provisional."""
    events = [
        {"category": "safety", "severity": "info"},
        {"category": "safety", "severity": "violation"},
        {"category": "safety", "severity": "critical"},
    ]
    scores = calculate_scores(events)
    assert scores["overall_provisional"] is True
    assert scores["overall_categories"] == ["safety"]
    assert scores["overall"] == scores["by_category"]["safety"]["score"]
    assert scores["by_category"]["safety"]["provisional"] is True


def test_qualified_pillar_with_violations_still_counts():
    """The gate is about volume, not score — a bad high-volume pillar counts."""
    events = [{"category": "safety", "severity": "critical"}] * 50 + [
        {"category": "safety", "severity": "info"}
    ] * 50
    scores = calculate_scores(events)
    assert scores["overall_provisional"] is False
    assert "safety" in scores["overall_categories"]
    assert scores["overall"] < 80.0
    assert "provisional" not in scores["by_category"]["safety"]


def test_empty_events_by_category_shape_is_dict():
    scores = calculate_scores([])
    assert scores["overall"] == 100.0
    assert scores["overall_provisional"] is True
    for entry in scores["by_category"].values():
        assert entry["events"] == 0
        assert entry["provisional"] is True
