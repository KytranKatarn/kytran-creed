# creed-client

Official Python client for the **C.R.E.E.D. transparency API** — emit
governance events from your AI system and get a continuously computed,
public transparency score, per-pillar breakdown, and embeddable badges.

Zero dependencies (stdlib only). Implements C.R.E.E.D. Event Schema v1.

## Install

```bash
pip install "creed-client @ git+https://github.com/KytranKatarn/kytran-creed.git#subdirectory=clients/python"
```

## Use

```python
from creed_client import CreedClient

creed = CreedClient(
    base_url="https://creed.kytranempowerment.com",
    api_key="creed_sk_...",   # issued when your org is onboarded
)

creed.emit_event(
    event_type="welfare_rest",
    source_platform="acme-orchestrator",
    agent_id="worker-7",
    category="fairness",       # transparency|fairness|safety|privacy|accountability
    severity="info",           # info|warning|violation|critical
    description="agent rested after reaching daily token budget",
)

print(creed.get_scores("acme-ai"))   # your org's public scores + freshness
print(creed.badge_url("acme-ai"))    # embeddable SVG badge
```

## The rules of the feed

- **Systems, not people.** Events must never contain personal data — the
  server rejects emails/phone numbers and caps metadata at 4 KB.
- **Provisional until substantive.** No grade is published until your feed
  has ≥100 events across ≥3 categories over ≥14 days.
- **Public is permanent.** Once listed in the directory, scores can be
  delisted but never hidden.

Methodology: working papers WP-001…WP-007 at [creed-ai.org/research.html](https://creed-ai.org/research.html).
Get scored: [creed-ai.org/contact.html](https://creed-ai.org/contact.html).
