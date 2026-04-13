BADGE_COLORS = {
    "A+": "#22c55e",
    "A": "#22c55e",
    "B+": "#3b82f6",
    "B": "#3b82f6",
    "C": "#eab308",
    "D": "#f97316",
    "F": "#ef4444",
}
BADGE_TEMPLATE = """<svg xmlns="http://www.w3.org/2000/svg" width="200" height="20">
  <linearGradient id="bg" x2="0" y2="100%">
    <stop offset="0" stop-color="#555"/>
    <stop offset="1" stop-color="#333"/>
  </linearGradient>
  <rect rx="3" width="200" height="20" fill="url(#bg)"/>
  <rect rx="3" x="110" width="90" height="20" fill="{color}"/>
  <text x="6" y="14" fill="#fff" font-family="Arial,sans-serif" font-size="11">C.R.E.E.D. {label}</text>
  <text x="155" y="14" fill="#fff" font-family="Arial,sans-serif" font-size="11" text-anchor="middle">{grade} ({score}%)</text>
</svg>"""
VALID_TYPES = {"overall", "transparency", "fairness", "safety", "privacy", "accountability"}


def generate_badge(badge_type: str, scores: dict) -> str | None:
    if badge_type not in VALID_TYPES:
        return None
    if badge_type == "overall":
        score = scores["overall"]
        grade = scores["grade"]
        label = "Overall"
    else:
        score = scores["by_category"].get(badge_type, 100.0)
        grade = _score_to_grade(score)
        label = badge_type.title()
    color = BADGE_COLORS.get(grade, "#6b7280")
    return BADGE_TEMPLATE.format(label=label, grade=grade, score=int(score), color=color)


def _score_to_grade(score: float) -> str:
    for threshold, grade in [(95, "A+"), (90, "A"), (85, "B+"), (80, "B"), (70, "C"), (60, "D")]:
        if score >= threshold:
            return grade
    return "F"
