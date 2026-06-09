"""creed-client — official Python client for the C.R.E.E.D. transparency API.

Emit governance events from your AI system to a C.R.E.E.D. scoring provider
(hosted Institute instance or your own self-hosted deployment) and read back
your public scores. Implements C.R.E.E.D. Event Schema v1 (ADR-004).

    from creed_client import CreedClient

    creed = CreedClient(
        base_url="https://api.creed-ai.org",
        api_key="creed_sk_...",          # tenant-scoped ingest key
    )
    creed.emit_event(
        event_type="welfare_rest",
        source_platform="acme-orchestrator",
        agent_id="worker-7",
        category="fairness",             # transparency|fairness|safety|privacy|accountability
        severity="info",                 # info|warning|violation|critical
        description="agent rested after reaching daily token budget",
    )
    print(creed.get_scores("acme-ai"))

Privacy contract: events describe SYSTEMS, never data subjects. The server
rejects descriptions/metadata containing emails or phone numbers, and caps
metadata at 4 KB.
"""

import json
import time
import urllib.error
import urllib.request

__version__ = "0.1.0"

CATEGORIES = {"transparency", "fairness", "safety", "privacy", "accountability"}
SEVERITIES = {"info", "warning", "violation", "critical"}
INCIDENT_SEVERITIES = {"low", "medium", "high", "critical"}


class CreedError(Exception):
    """API-level error: carries HTTP status and the server's error body."""

    def __init__(self, status, body):
        self.status = status
        self.body = body
        super().__init__(f"HTTP {status}: {body}")


class CreedClient:
    def __init__(self, base_url, api_key=None, timeout=10, retries=2, backoff=1.5):
        """
        base_url: scoring provider root, e.g. https://creed.kytranempowerment.com
        api_key:  tenant-scoped 'creed_sk_…' key (required for ingest; reads are public)
        retries:  retry count for transient failures (5xx / network), exponential backoff
        """
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.retries = retries
        self.backoff = backoff

    # ── ingest (requires api_key) ───────────────────────────────────────────

    def emit_event(
        self,
        event_type,
        source_platform,
        agent_id,
        category,
        severity,
        description,
        agent_name=None,
        metadata=None,
    ):
        """POST a governance event. Returns the new event id."""
        if category not in CATEGORIES:
            raise ValueError(f"category must be one of {sorted(CATEGORIES)}")
        if severity not in SEVERITIES:
            raise ValueError(f"severity must be one of {sorted(SEVERITIES)}")
        body = {
            "event_type": event_type,
            "source_platform": source_platform,
            "agent_id": agent_id,
            "category": category,
            "severity": severity,
            "description": description,
            "metadata": metadata or {},
        }
        if agent_name:
            body["agent_name"] = agent_name
        return self._request("POST", "/api/v1/events", body, auth=True)["event_id"]

    def file_incident(self, severity, title, disclosed=False, **fields):
        """File an AI incident (never auto-published; visibility gated by 'disclosed')."""
        if severity not in INCIDENT_SEVERITIES:
            raise ValueError(f"severity must be one of {sorted(INCIDENT_SEVERITIES)}")
        body = {"severity": severity, "title": title, "disclosed": disclosed, **fields}
        return self._request("POST", "/api/v1/incidents", body, auth=True)

    # ── public reads (no key needed) ────────────────────────────────────────

    def get_scores(self, org_slug=None, days=30):
        """Scores for an org (or the provider's own institute scores when None)."""
        path = f"/api/v1/orgs/{org_slug}/scores" if org_slug else "/api/v1/scores"
        return self._request("GET", f"{path}?days={days}")

    def list_orgs(self):
        """Public directory of scored organizations."""
        return self._request("GET", "/api/v1/orgs")

    def badge_url(self, org_slug, badge_type="overall"):
        """Embeddable SVG badge URL for an org."""
        return f"{self.base_url}/api/v1/badge/{org_slug}/{badge_type}"

    # ── internals ───────────────────────────────────────────────────────────

    def _request(self, method, path, body=None, auth=False):
        headers = {"Content-Type": "application/json"}
        if auth:
            if not self.api_key:
                raise CreedError(0, "api_key required for ingest calls")
            headers["Authorization"] = f"Bearer {self.api_key}"
        data = json.dumps(body).encode() if body is not None else None
        last_err = None
        for attempt in range(self.retries + 1):
            req = urllib.request.Request(
                self.base_url + path, data=data, headers=headers, method=method
            )
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    return json.loads(resp.read().decode() or "{}")
            except urllib.error.HTTPError as e:
                detail = e.read().decode(errors="replace")[:500]
                # 4xx are contract errors — never retried (incl. 429: respect the limit)
                if e.code < 500:
                    raise CreedError(e.code, detail) from None
                last_err = CreedError(e.code, detail)
            except urllib.error.URLError as e:
                last_err = CreedError(0, str(e.reason))
            if attempt < self.retries:
                time.sleep(self.backoff * (2**attempt))
        raise last_err
