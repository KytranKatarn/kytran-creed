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
  <text x="155" y="14" fill="#fff" font-family="Arial,sans-serif" font-size="11" text-anchor="middle">{right}</text>
</svg>"""
VALID_TYPES = {"overall", "transparency", "fairness", "safety", "privacy", "accountability"}

# Tenant badges carry a third segment: the verification tier (ADR-004 §5) —
# a SELF-REPORTED A+ visibly claims less than a SIGNED B+.
TIER_BADGE_TEMPLATE = """<svg xmlns="http://www.w3.org/2000/svg" width="262" height="20">
  <linearGradient id="bg" x2="0" y2="100%">
    <stop offset="0" stop-color="#555"/>
    <stop offset="1" stop-color="#333"/>
  </linearGradient>
  <rect rx="3" width="262" height="20" fill="url(#bg)"/>
  <rect x="110" width="90" height="20" fill="{color}"/>
  <rect rx="3" x="200" width="62" height="20" fill="#1f2430"/>
  <rect x="200" width="3" height="20" fill="#1f2430"/>
  <text x="6" y="14" fill="#fff" font-family="Arial,sans-serif" font-size="11">C.R.E.E.D. {label}</text>
  <text x="155" y="14" fill="#fff" font-family="Arial,sans-serif" font-size="11" text-anchor="middle">{right}</text>
  <text x="231" y="14" fill="#9aa3b8" font-family="Arial,sans-serif" font-size="9" text-anchor="middle">{tier}</text>
</svg>"""

TIER_SHORT = {"self_reported": "SELF", "signed": "SIGNED", "audited": "AUDITED"}


def generate_badge(
    badge_type: str, scores: dict, provisional: bool = False, tier: str | None = None
) -> str | None:
    if badge_type not in VALID_TYPES:
        return None
    template = BADGE_TEMPLATE
    extra = {}
    if tier:
        template = TIER_BADGE_TEMPLATE
        extra = {"tier": TIER_SHORT.get(tier, tier.upper()[:7])}
    # Provisional gate (ADR-004 §5): the feed lacks substance — gray badge, no grade.
    if provisional:
        label = "Overall" if badge_type == "overall" else badge_type.title()
        return template.format(label=label, right="PROVISIONAL", color="#6b7280", **extra)
    if badge_type == "overall":
        score = scores["overall"]
        grade = scores["grade"]
        label = "Overall"
    else:
        cat_data = scores["by_category"].get(badge_type, 100.0)
        # by_category values are now {score, events, grade} dicts; support legacy float too
        if isinstance(cat_data, dict):
            score = cat_data.get("score", 100.0)
            grade = cat_data.get("grade") or _score_to_grade(score)
        else:
            score = cat_data
            grade = _score_to_grade(score)
        label = badge_type.title()
    color = BADGE_COLORS.get(grade, "#6b7280")
    return template.format(label=label, right=f"{grade} ({int(score)}%)", color=color, **extra)


def _score_to_grade(score: float) -> str:
    for threshold, grade in [(95, "A+"), (90, "A"), (85, "B+"), (80, "B"), (70, "C"), (60, "D")]:
        if score >= threshold:
            return grade
    return "F"
