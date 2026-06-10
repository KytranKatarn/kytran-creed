"""EN/FR translations for C.R.E.E.D. standalone."""

SUPPORTED_LANGS = frozenset({"en", "fr"})

TRANSLATIONS = {
    "en": {
        "nav.dashboard": "Dashboard",
        "nav.events": "Events",
        "nav.incidents": "Incidents",
        "nav.aia": "Impact Assessments",
        "nav.settings": "Settings",
        "nav.logout": "Logout",
        "lang.current": "EN",
        "lang.switch": "FR",
        "lang.switch_to": "Switch to French",
        "score.overall": "Overall Score",
        "score.transparency": "Transparency",
        "score.fairness": "Fairness",
        "score.safety": "Safety",
        "score.privacy": "Privacy",
        "score.accountability": "Accountability",
        "score.environmental": "Environmental",
        "badge.provisional": "PROVISIONAL",
        "badge.self_reported": "SELF-REPORTED",
        "footer.powered": "Powered by C.R.E.E.D.",
        "flash.lang_set": "Language set to English.",
    },
    "fr": {
        "nav.dashboard": "Tableau de bord",
        "nav.events": "Événements",
        "nav.incidents": "Incidents",
        "nav.aia": "Évaluations d'impact",
        "nav.settings": "Paramètres",
        "nav.logout": "Déconnexion",
        "lang.current": "FR",
        "lang.switch": "EN",
        "lang.switch_to": "Passer à l'anglais",
        "score.overall": "Score global",
        "score.transparency": "Transparence",
        "score.fairness": "Équité",
        "score.safety": "Sécurité",
        "score.privacy": "Vie privée",
        "score.accountability": "Responsabilité",
        "score.environmental": "Environnement",
        "badge.provisional": "PROVISOIRE",
        "badge.self_reported": "AUTO-DÉCLARÉ",
        "footer.powered": "Propulsé par C.R.E.E.D.",
        "flash.lang_set": "Langue définie sur le français.",
    },
}


def t(key: str, lang: str = "en") -> str:
    """Translate key into lang; falls back to EN, then key itself."""
    lang = lang if lang in SUPPORTED_LANGS else "en"
    return TRANSLATIONS[lang].get(key) or TRANSLATIONS["en"].get(key) or key


def get_translations(lang: str) -> dict:
    lang = lang if lang in SUPPORTED_LANGS else "en"
    return TRANSLATIONS[lang]
