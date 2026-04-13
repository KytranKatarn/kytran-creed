from dataclasses import dataclass, field
from typing import Optional

VALID_EVENT_TYPES = {"agent_action", "decision", "violation", "welfare_check", "ethics_review"}
VALID_CATEGORIES = {"transparency", "fairness", "safety", "privacy", "accountability"}
VALID_SEVERITIES = {"info", "warning", "violation", "critical"}
REQUIRED_EVENT_FIELDS = {"event_type", "source_platform", "agent_id", "category", "severity", "description"}


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
        if self.event_type and self.event_type not in VALID_EVENT_TYPES:
            errors.append(f"Invalid event_type: {self.event_type}")
        if self.category and self.category not in VALID_CATEGORIES:
            errors.append(f"Invalid category: {self.category}")
        if self.severity and self.severity not in VALID_SEVERITIES:
            errors.append(f"Invalid severity: {self.severity}")
        return errors
