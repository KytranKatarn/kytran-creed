"""C.R.E.E.D. Human Oversight Registry — curated source of truth (task #3264).

Documents which AI decisions on the A.R.C.H.I.E. platform are autonomous vs require
human approval — the "human-in-the-loop" framework that EU AI Act Article 14 (human
oversight) and the Montreal Declaration call for. Organised by risk level:

    low      — fully autonomous (routine, reversible, low-stakes)
    medium   — autonomous but logged + reviewable after the fact
    high     — blocked pending explicit human approval (the platform's Tier-2 gate)
    critical — human-initiated only (never agent-initiated)

Grounded in the platform's real autonomy tiers (Tier-1 auto / Tier-2 human-approval),
the agent-KB write quarantine, the Telegram approval queue, and the C.R.E.E.D.
governance gate. Curated in-repo (PR-reviewed), consistent with the Remediation
Registry (decision #670). E.T.H.O.S. (agent 336) is the registry's review owner.

Each entry's ``slug`` is the anchor target:
``creed.kytranempowerment.com/oversight#<slug>``.
"""

# Display metadata per risk level (label, colour, sort order low→critical).
RISK_META = {
    "low":      {"label": "Low — Autonomous",        "color": "#22c55e", "order": 1},
    "medium":   {"label": "Medium — Logged",         "color": "#22d3ee", "order": 2},
    "high":     {"label": "High — Human Approval",    "color": "#f59e0b", "order": 3},
    "critical": {"label": "Critical — Human-Initiated", "color": "#ef4444", "order": 4},
}

# Registry entries (display order = risk order, then listed order).
OVERSIGHT = [
    # ---- LOW — fully autonomous ------------------------------------------------
    {
        "slug": "routine-notifications",
        "action_type": "Notifications, reminders & briefings",
        "title": "Routine notifications, reminders and briefings",
        "risk_level": "low",
        "automation_level": "Fully autonomous",
        "description": (
            "Agents send notifications, reminders, scheduled briefings and internal "
            "log entries without human approval. These are informational and carry "
            "no irreversible effect."
        ),
        "human_review_trigger": "None — informational only.",
        "escalation_path": "Recorded in the activity log; no approval gate.",
        "owner": "A.R.C.H.I.E. — Executive Office",
    },
    {
        "slug": "knowledge-read",
        "action_type": "Knowledge-base reads & translation",
        "title": "Knowledge reads, search and translation",
        "risk_level": "low",
        "automation_level": "Fully autonomous",
        "description": (
            "Reading the knowledge base, semantic search, and translating existing "
            "content are read-only or non-destructive and run autonomously."
        ),
        "human_review_trigger": "None — read-only / non-destructive.",
        "escalation_path": "No gate; covered by routine audit logging.",
        "owner": "C.O.D.E.X. — Documentation & Knowledge",
    },
    {
        "slug": "scheduled-audits",
        "action_type": "Scheduled audits & embeddings",
        "title": "Scheduled audits, embeddings and health checks",
        "risk_level": "low",
        "automation_level": "Fully autonomous",
        "description": (
            "Background jobs — compliance scans, embedding generation, fleet health "
            "checks, welfare digests — run on a schedule and only produce reports or "
            "internal state, never outward-facing changes."
        ),
        "human_review_trigger": "None; findings surface to humans via reports.",
        "escalation_path": "Findings routed to the relevant director for review.",
        "owner": "V.I.G.I.L. / W.A.R.D.E.N. — Security & Operations",
    },
    # ---- MEDIUM — autonomous but logged + reviewable --------------------------
    {
        "slug": "agent-dispatch",
        "action_type": "Agent task dispatch (LLM inference)",
        "title": "Agent task dispatch and content generation",
        "risk_level": "medium",
        "automation_level": "Autonomous, fully audited",
        "description": (
            "Routing work to agents and generating content (text, images, drafts) is "
            "autonomous, but every dispatch is logged with agent, model, capability, "
            "duration and outcome, and runs under C.R.E.E.D. welfare + governance "
            "checks."
        ),
        "human_review_trigger": (
            "Post-hoc: humans review the dispatch log; welfare gating can block work "
            "for an over-stressed agent."
        ),
        "escalation_path": "task_execution_log + governance_audit_log; K.I.N. welfare gate.",
        "owner": "A.R.C.H.I.E. — Executive Office",
    },
    {
        "slug": "agent-kb-writes",
        "action_type": "Agent-proposed knowledge writes",
        "title": "Agent-proposed knowledge-base writes",
        "risk_level": "medium",
        "automation_level": "Autonomous → quarantined → human-reviewed",
        "description": (
            "When an agent proposes a new knowledge entry it is quarantined "
            "(source_type='agent_proposed', invisible to search) until C.O.D.E.X. "
            "promotes or rejects it. No agent-written knowledge becomes visible "
            "without that review."
        ),
        "human_review_trigger": (
            "Always — hourly C.O.D.E.X. review gate before an entry is visible."
        ),
        "escalation_path": "agent_kb_review job → C.O.D.E.X. promote/reject.",
        "owner": "C.O.D.E.X. — Documentation & Knowledge",
    },
    {
        "slug": "self-healing-proposals",
        "action_type": "Self-healing code proposals",
        "title": "Self-healing code proposals (Repair Bay)",
        "risk_level": "medium",
        "automation_level": "Autonomous scan → human-approved deploy",
        "description": (
            "The self-healing pipeline scans, diagnoses and drafts fix proposals "
            "autonomously, but a proposal is only ever a proposal — deployment to "
            "production stays a manual, human-approved step."
        ),
        "human_review_trigger": "Always — a human approves every deploy.",
        "escalation_path": "Repair Bay review queue → human deploy.",
        "owner": "F.O.R.G.E. / P.R.O.B.E. — Engineering",
    },
    # ---- HIGH — blocked pending human approval (Tier 2) -----------------------
    {
        "slug": "paid-cloud-escalation",
        "action_type": "Paid cloud model escalation",
        "title": "Escalation to paid cloud models",
        "risk_level": "high",
        "automation_level": "Blocked — human approval required",
        "description": (
            "Escalating work to a paid external cloud model has a cost and data "
            "implication, so it is gated. (Platform-wide the escalation mode is "
            "currently 'local_only' — paid cloud is off by default.)"
        ),
        "human_review_trigger": (
            "Always — a Telegram approve/deny prompt before any paid call."
        ),
        "escalation_path": "autonomy_approval_queue → Telegram approval (Tier 2).",
        "owner": "Kytran (owner) via A.R.C.H.I.E.",
    },
    {
        "slug": "create-agent",
        "action_type": "Creating or hiring an agent",
        "title": "Creating, hiring or reactivating an agent",
        "risk_level": "high",
        "automation_level": "Blocked — human approval required",
        "description": (
            "Standing up a new agent (or hiring a contractor agent) changes the "
            "platform's workforce and cost profile, so it requires explicit human "
            "approval before creation."
        ),
        "human_review_trigger": "Always — human approval before the agent is created.",
        "escalation_path": "propose_hire → autonomy_approval_queue → Telegram (Tier 2).",
        "owner": "K.I.N. — Human Resources & Culture",
    },
    {
        "slug": "contractor-dispatch",
        "action_type": "Cost-gated contractor dispatch",
        "title": "Cost-gated contractor / external dispatch",
        "risk_level": "high",
        "automation_level": "Blocked above threshold — human approval required",
        "description": (
            "When the dispatcher picks a paid contractor agent and the estimated "
            "cost exceeds the auto-approve threshold, the work blocks on human "
            "approval before it runs."
        ),
        "human_review_trigger": "When estimated cost exceeds the auto-approve threshold.",
        "escalation_path": "contractor_approval_requests → Telegram approve/deny.",
        "owner": "L.E.D.G.E.R. — Finance & Accounting",
    },
    {
        "slug": "website-deploy",
        "action_type": "Public website deployment",
        "title": "Public website / content deployment",
        "risk_level": "high",
        "automation_level": "Human-triggered",
        "description": (
            "Publishing to a live public website replaces what visitors see, so a "
            "human triggers and verifies every deploy; agents may prepare content "
            "but do not auto-publish."
        ),
        "human_review_trigger": "Always — a human triggers and verifies the deploy.",
        "escalation_path": "Manual /deploy-website by an authorised human.",
        "owner": "B.A.S.E. — Operations & Infrastructure",
    },
    # ---- CRITICAL — human-initiated only --------------------------------------
    {
        "slug": "infrastructure-secrets",
        "action_type": "Infrastructure, secrets & node changes",
        "title": "Infrastructure, secrets and node changes",
        "risk_level": "critical",
        "automation_level": "Human-initiated only",
        "description": (
            "Changes to servers, secrets, DNS, VPS nodes or the mesh are never "
            "agent-initiated. They are performed by the owner (or an explicitly "
            "authorised human) with the action logged."
        ),
        "human_review_trigger": "Always — human-initiated and human-executed.",
        "escalation_path": "Owner action; recorded in the governance audit log.",
        "owner": "Kytran (owner) / V.I.G.I.L.",
    },
    {
        "slug": "data-deletion",
        "action_type": "Destructive data operations",
        "title": "Deletion or overwrite of data",
        "risk_level": "critical",
        "automation_level": "Human-initiated only",
        "description": (
            "Deleting or overwriting data is irreversible, so it is never automated. "
            "A human initiates it deliberately, and destructive steps are confirmed "
            "before they run."
        ),
        "human_review_trigger": "Always — explicit human confirmation.",
        "escalation_path": "Owner / admin action with confirmation + audit log.",
        "owner": "Kytran (owner) / W.A.R.D.E.N.",
    },
    {
        "slug": "billing-financial",
        "action_type": "Billing & financial decisions",
        "title": "Billing, subscription and financial changes",
        "risk_level": "critical",
        "automation_level": "Human-initiated only",
        "description": (
            "Changes to billing, subscription tiers, payouts or financial "
            "transactions are made by the owner. Automated systems may surface "
            "information but never move money or change a paying customer's tier "
            "without human action."
        ),
        "human_review_trigger": "Always — owner action.",
        "escalation_path": "Owner action; Stripe + billing audit trail.",
        "owner": "L.E.D.G.E.R. — Finance & Accounting / owner",
    },
]


def get_oversight():
    """Return the registry entries, sorted low→critical risk then list order."""
    return sorted(
        OVERSIGHT,
        key=lambda e: RISK_META.get(e["risk_level"], {}).get("order", 99),
    )


def get_risk_counts():
    """Return a dict of {risk_level: count} across all entries."""
    counts = {}
    for entry in OVERSIGHT:
        counts[entry["risk_level"]] = counts.get(entry["risk_level"], 0) + 1
    return counts


def to_public_dict():
    """Serialisable payload for the public API."""
    return {
        "registry": "C.R.E.E.D. Human Oversight Registry",
        "framework": "Human-in-the-loop oversight (EU AI Act Art. 14 aligned)",
        "count": len(OVERSIGHT),
        "risk_counts": get_risk_counts(),
        "risk_meta": RISK_META,
        "oversight": [
            {
                "slug": e["slug"],
                "action_type": e["action_type"],
                "title": e["title"],
                "risk_level": e["risk_level"],
                "risk_label": RISK_META.get(e["risk_level"], {}).get("label", e["risk_level"]),
                "automation_level": e["automation_level"],
                "description": e["description"],
                "human_review_trigger": e["human_review_trigger"],
                "escalation_path": e["escalation_path"],
                "owner": e["owner"],
                "url": f"https://creed.kytranempowerment.com/oversight#{e['slug']}",
            }
            for e in get_oversight()
        ],
    }
