"""C.R.E.E.D. Event Schema — the open standard page (Phase 2 launch, #3269).

Human-readable spec at /standard; the machine-readable JSON Schema lives at
/api/v1/schema (api_routes.py). Both are generated/derived from the constants
in models.py so the published standard cannot drift from the validator.
"""

from flask import Blueprint, render_template

from kytran_creed.models import (
    METADATA_MAX_BYTES,
    REQUIRED_EVENT_FIELDS,
    SCHEMA_VERSION,
    VALID_CATEGORIES,
    VALID_SEVERITIES,
)
from kytran_creed.routes.orgs_routes import (
    PROVISIONAL_MIN_CATEGORIES,
    PROVISIONAL_MIN_EVENTS,
    PROVISIONAL_MIN_SPAN_DAYS,
)
from kytran_creed.services.scoring_engine import SEVERITY_WEIGHTS
from kytran_creed.tenant_auth import KEY_RATE_LIMIT, KEY_RATE_WINDOW

standard_bp = Blueprint("standard", __name__)


@standard_bp.route("/standard")
def standard_page():
    return render_template(
        "standard.html",
        schema_version=SCHEMA_VERSION,
        required_fields=sorted(REQUIRED_EVENT_FIELDS),
        categories=sorted(VALID_CATEGORIES),
        severities=[(s, SEVERITY_WEIGHTS[s]) for s in ("info", "warning", "violation", "critical")],
        metadata_max=METADATA_MAX_BYTES,
        rate_limit=KEY_RATE_LIMIT,
        rate_window=KEY_RATE_WINDOW,
        gate={
            "events": PROVISIONAL_MIN_EVENTS,
            "categories": PROVISIONAL_MIN_CATEGORIES,
            "days": PROVISIONAL_MIN_SPAN_DAYS,
        },
    )
