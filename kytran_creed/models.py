from dataclasses import dataclass, field
from typing import Optional

VALID_CATEGORIES = {"transparency", "fairness", "safety", "privacy", "accountability", "environmental"}
VALID_SEVERITIES = {"info", "warning", "violation", "critical"}
REQUIRED_EVENT_FIELDS = {"event_type", "source_platform", "agent_id", "category", "severity", "description"}

# C.R.E.E.D. Event Schema version — bump on any breaking change to the event
# object. Ingest tolerates (and ignores) an optional `schema_version` field so
# emitters can pin the version they target.
SCHEMA_VERSION = "1"

METADATA_MAX_BYTES = 4096


def event_json_schema(base_url: str = "https://api.creed-ai.org") -> dict:
    """JSON Schema (draft 2020-12) for the v1 governance event — generated
    from the same constants `GovernanceEvent.validate()` enforces, so the
    published standard can never drift from what the API actually accepts."""
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"{base_url}/api/v1/schema",
        "title": "C.R.E.E.D. Governance Event",
        "description": (
            "A single governance event emitted by an AI system operator. "
            "Events describe systems, never people — submissions containing "
            "personal data (emails, phone numbers) are rejected at the door."
        ),
        "type": "object",
        "required": sorted(REQUIRED_EVENT_FIELDS),
        "properties": {
            "event_type": {
                "type": "string",
                "description": "Operator-defined event name, e.g. 'welfare_rest', 'bias_sample', 'access_review'",
            },
            "source_platform": {
                "type": "string",
                "description": "The emitting system/orchestrator identifier",
            },
            "agent_id": {
                "type": "string",
                "description": "Stable identifier of the AI agent/model/component the event concerns",
            },
            "agent_name": {
                "type": "string",
                "description": "Optional human-readable agent name",
            },
            "category": {
                "type": "string",
                "enum": sorted(VALID_CATEGORIES),
                "description": "Scoring pillar the event belongs to",
            },
            "severity": {
                "type": "string",
                "enum": sorted(VALID_SEVERITIES),
                "description": "Governance weight: info=0, warning=1, violation=3, critical=5",
            },
            "description": {
                "type": "string",
                "description": "What happened, in systems language. No personal data.",
            },
            "metadata": {
                "type": "object",
                "description": f"Optional structured context, max {METADATA_MAX_BYTES} bytes serialized",
            },
            "schema_version": {
                "type": "string",
                "description": f"Optional schema version the emitter targets (current: '{SCHEMA_VERSION}')",
            },
        },
        "additionalProperties": True,
    }


@dataclass
class GovernanceEvent:
    event_type: str
    source_platform: str
    agent_id: str
    agent_name: str
    category: str
    severity: str
    description: str
    metadata: dict = field(default_factory=dict)
    timestamp: Optional[str] = None
    id: Optional[int] = None

    def validate(self) -> list[str]:
        errors = []
        for f in REQUIRED_EVENT_FIELDS:
            if not getattr(self, f, None):
                errors.append(f"Missing required field: {f}")
        if self.category and self.category not in VALID_CATEGORIES:
            errors.append(f"Invalid category: {self.category}")
        if self.severity and self.severity not in VALID_SEVERITIES:
            errors.append(f"Invalid severity: {self.severity}")
        return errors
