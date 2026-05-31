"""C.R.E.E.D. Remediation Registry — curated source of truth.

Each entry documents a publicly-acknowledged limitation of a C.R.E.E.D.-monitored
product and the governance position on it: why it exists, what is being done about
it, who owns it, and its current status. This is *curated* governance content, not
event data — it lives in-repo (not a DB table) on purpose so that every change to
what the public accountability page states passes through PR review.

Linked from product "Known Limitations" sections (e.g. what-the-fact.tech
/methodology). Each entry's ``slug`` is the anchor target:
``creed.kytranempowerment.com/remediation#<slug>``.

Status vocabulary:
    accepted    — inherent design trade-off. Documented mitigation, not a defect
                  we intend to "fix". Transparency = naming it honestly.
    in_progress — actively being improved.
    planned     — on the roadmap, not yet started.
    resolved    — addressed; kept for the historical record.
"""

# Display metadata for each status (label + accent colour, used by the template).
STATUS_META = {
    "accepted": {"label": "Accepted Trade-off", "color": "#8b5cf6"},
    "in_progress": {"label": "In Progress", "color": "#22d3ee"},
    "planned": {"label": "Planned", "color": "#f59e0b"},
    "resolved": {"label": "Resolved", "color": "#10b981"},
}

# Registry entries. Order here is the display order.
REMEDIATIONS = [
    {
        "slug": "wtf-llm-training-cutoff",
        "source_product": "What The Fact",
        "limitation_title": "LLM analysis is bounded by the model's training cutoff",
        "limitation_text": (
            "LLM analysis is based on training data (cutoff 2024) — models do not "
            "have internet access or real-time fact databases."
        ),
        "category": "AI Model Constraints",
        "status": "accepted",
        "description": (
            "Local language models reason from their training corpus; they cannot "
            "look up events that post-date that corpus or query a live fact store. "
            "This is a property of how the models are run, not a configuration bug."
        ),
        "remediation_plan": (
            "Facts are taken from the live article text, not the model's memory: "
            "summaries are extractive (drawn from the published body), and the LLM "
            "is used for framing, tone and bias interpretation rather than as a "
            "source of factual claims. A retrieval-augmented fact-check path "
            "(grounding on a live evidence store) is on the research roadmap."
        ),
        "owner": "D.A.R.W.I.N. — Research & Development",
        "target_date": None,
        "updated_at": "2026-05-31",
    },
    {
        "slug": "wtf-bias-vs-human-consensus",
        "source_product": "What The Fact",
        "limitation_title": "Bias scores may not match human expert consensus",
        "limitation_text": (
            "Bias scoring reflects the LLM's interpretation of language patterns; "
            "it may not match human expert consensus in all cases."
        ),
        "category": "Bias & Fairness",
        "status": "in_progress",
        "description": (
            "A single model's reading of loaded language is one signal among "
            "several. Reasonable analysts — and reasonable models — can disagree "
            "on where a given article sits on the spectrum."
        ),
        "remediation_plan": (
            "Bias is computed from multiple independent signals (LLM language "
            "analysis, outlet editorial-stance priors, and a separate DistilBERT "
            "NLI model) rather than one verdict, and the rationale is shown so "
            "readers can judge it themselves. Ongoing calibration measures the "
            "scorer against outlet editorial baselines."
        ),
        "owner": "B.I.A.S. — News & Media",
        "target_date": None,
        "updated_at": "2026-05-31",
    },
    {
        "slug": "wtf-geolocation-province-fallback",
        "source_product": "What The Fact",
        "limitation_title": "Geolocation falls back to source province at low confidence",
        "limitation_text": (
            "Geolocation uses source province as fallback when AI confidence is "
            "low (<0.5)."
        ),
        "category": "Data Coverage",
        "status": "in_progress",
        "description": (
            "When the extractor cannot confidently locate a story, it attributes "
            "it to the publishing outlet's province rather than guessing a precise "
            "location it is not sure of."
        ),
        "remediation_plan": (
            "Province-level fallbacks are labelled transparently rather than "
            "presented as precise geolocation. The L.O.C.A.L. agent's "
            "geo-extraction is being improved to raise the share of articles that "
            "clear the confidence threshold."
        ),
        "owner": "L.O.C.A.L. — News & Media",
        "target_date": None,
        "updated_at": "2026-05-31",
    },
    {
        "slug": "wtf-priority-article-coverage",
        "source_product": "What The Fact",
        "limitation_title": "Not every article receives full LLM analysis",
        "limitation_text": (
            "Not all articles receive full AI analysis — only priority articles "
            "(top 20/cycle) get LLM treatment; all others receive heuristic + "
            "source-editorial bias scoring."
        ),
        "category": "Throughput & Coverage",
        "status": "in_progress",
        "description": (
            "Full LLM analysis is compute-bound. To keep the feed current, each "
            "ingest cycle prioritises the highest-signal articles for deep "
            "analysis and applies lighter heuristic + editorial scoring to the rest."
        ),
        "remediation_plan": (
            "Analysis throughput is being scaled across the agent fleet and a "
            "backlog drains lower-priority articles toward full coverage over "
            "time. Articles that have not yet had full LLM analysis are scored by "
            "transparent heuristic + outlet-editorial methods in the interim."
        ),
        "owner": "F.A.C.T. — News & Media",
        "target_date": None,
        "updated_at": "2026-05-31",
    },
    {
        "slug": "wtf-outlet-bias-rolling-average",
        "source_product": "What The Fact",
        "limitation_title": "Outlet bias profiles are rolling averages, seeded for new outlets",
        "limitation_text": (
            "Outlet bias profiles are rolling averages; new outlets are seeded "
            "from editorial stance data and refined over time."
        ),
        "category": "Bias & Fairness",
        "status": "accepted",
        "description": (
            "An outlet's bias profile is a moving aggregate of its analysed "
            "coverage. A newly added outlet has little history, so it starts from "
            "a documented editorial-stance prior and converges as articles "
            "accumulate."
        ),
        "remediation_plan": (
            "This is the intended design: profiles update as evidence accumulates "
            "rather than being fixed labels. Seed priors are sourced from "
            "published editorial-stance research and are superseded by measured "
            "behaviour as the sample grows."
        ),
        "owner": "B.I.A.S. — News & Media",
        "target_date": None,
        "updated_at": "2026-05-31",
    },
    {
        "slug": "wtf-paywalled-body-text",
        "source_product": "What The Fact",
        "limitation_title": "Paywalled articles are analysed from title + summary only",
        "limitation_text": (
            "Paywalled articles (Postmedia, Torstar) have limited body text — AI "
            "analysis relies on title + Open Graph description only."
        ),
        "category": "Data Coverage",
        "status": "accepted",
        "description": (
            "Where a publisher gates the article body behind a paywall, the full "
            "text is not lawfully or technically available to ingest, so analysis "
            "is limited to the headline and the publicly-served summary metadata."
        ),
        "remediation_plan": (
            "Paywalled items are analysed only from the publicly-available title "
            "and Open Graph description, and this reduced basis is disclosed rather "
            "than hidden. We do not bypass paywalls to obtain body text."
        ),
        "owner": "F.A.C.T. — News & Media",
        "target_date": None,
        "updated_at": "2026-05-31",
    },
    {
        "slug": "wtf-distilbert-canadian-framing",
        "source_product": "What The Fact",
        "limitation_title": "The DistilBERT signal is US-trained and used as a second opinion",
        "limitation_text": (
            "DistilBERT Signal 3 (US-trained NLI model) may not map cleanly to "
            "Canadian political framing; treated as a second opinion, not ground "
            "truth."
        ),
        "category": "Bias & Fairness",
        "status": "in_progress",
        "description": (
            "The supplementary DistilBERT natural-language-inference model was "
            "trained primarily on US data, so its read of Canadian political "
            "framing can be imperfect."
        ),
        "remediation_plan": (
            "Its output is weighted as one second-opinion signal, never as ground "
            "truth, and is cross-checked against the LLM and editorial signals. A "
            "Canadian-framing fine-tune is planned to improve its domain fit."
        ),
        "owner": "V.E.R.I.F.Y. — News & Media",
        "target_date": None,
        "updated_at": "2026-05-31",
    },
]


def get_remediations():
    """Return the registry entries (display order)."""
    return REMEDIATIONS


def get_status_counts():
    """Return a dict of {status: count} across all entries."""
    counts = {}
    for entry in REMEDIATIONS:
        counts[entry["status"]] = counts.get(entry["status"], 0) + 1
    return counts


def to_public_dict():
    """Serialisable payload for the public API.

    Includes per-status display metadata so external consumers (e.g.
    creed-ai.org) can render badges without duplicating the vocabulary.
    """
    return {
        "registry": "C.R.E.E.D. Remediation Registry",
        "count": len(REMEDIATIONS),
        "status_counts": get_status_counts(),
        "status_meta": STATUS_META,
        "remediations": [
            {
                "slug": e["slug"],
                "source_product": e["source_product"],
                "title": e["limitation_title"],
                "limitation": e["limitation_text"],
                "category": e["category"],
                "status": e["status"],
                "status_label": STATUS_META.get(e["status"], {}).get("label", e["status"]),
                "description": e["description"],
                "remediation_plan": e["remediation_plan"],
                "owner": e["owner"],
                "target_date": e["target_date"],
                "updated_at": e["updated_at"],
                "url": f"https://creed.kytranempowerment.com/remediation#{e['slug']}",
            }
            for e in REMEDIATIONS
        ],
    }
