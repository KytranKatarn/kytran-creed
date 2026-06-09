"""Multi-tenant API-key auth + ingest guards (task #3269 P1.2, ADR-004).

External orgs authenticate event/incident ingestion with ``Authorization:
Bearer creed_sk_…`` keys scoped to a tenant. Requests WITHOUT a key fall back
to the Institute tenant (the hub's own LAN feed predates keys — it switches to
an explicit key in P2, after which keyless ingest can be disabled).

Guards applied to key-authenticated ingest:
- per-key rate limit (in-memory sliding window, same model as the per-IP
  limiter in public_routes — per-worker, so the effective limit is
  RATE * worker_count)
- metadata size cap (4 KB)
- PII firewall: events describe SYSTEMS, never data subjects. Heuristics are
  deliberately conservative (emails, international/NA phone formats) to avoid
  false-positiving IPs and version strings.
"""

import hashlib
import logging
import re
import secrets
import time
from collections import defaultdict, deque

from flask import jsonify, request

from kytran_creed.pg import get_pg

logger = logging.getLogger(__name__)

KEY_PREFIX = "creed_sk_"
KEY_RATE_LIMIT = 600  # requests per key
KEY_RATE_WINDOW = 60  # seconds
METADATA_MAX_BYTES = 4096

_key_hits: dict[str, deque] = defaultdict(deque)

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]{2,}")
# Phones: leading + (international) or NNN-NNN-NNNN (NA). Plain digit runs,
# IPs, and version strings intentionally do NOT match.
_PHONE_RE = re.compile(r"(?:\+\d[\d\s().-]{8,}\d)|(?:\b\d{3}[-.\s]\d{3}[-.\s]\d{4}\b)")


def _hash_key(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def generate_api_key() -> tuple[str, str]:
    """Returns (plaintext_key, sha256_hash). Plaintext is shown exactly once."""
    raw = KEY_PREFIX + secrets.token_urlsafe(32)
    return raw, _hash_key(raw)


def _rate_limited(key_hash: str) -> bool:
    now = time.time()
    hits = _key_hits[key_hash]
    cutoff = now - KEY_RATE_WINDOW
    while hits and hits[0] < cutoff:
        hits.popleft()
    if len(hits) >= KEY_RATE_LIMIT:
        return True
    hits.append(now)
    return False


def resolve_tenant():
    """Resolve the calling tenant from the Authorization header.

    Returns (tenant_id, error_response):
    - no Authorization header        → (None, None)   — caller uses institute fallback
    - valid active key/tenant        → (uuid_str, None)
    - invalid / inactive / suspended → (None, (response, status))
    """
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None, None
    token = auth[7:].strip()
    if not token.startswith(KEY_PREFIX):
        return None, (jsonify({"success": False, "error": "invalid API key"}), 401)

    pg = get_pg()
    if not pg:
        return None, (
            jsonify({"success": False, "error": "multi-tenant mode requires Postgres"}),
            503,
        )
    key_hash = _hash_key(token)
    if _rate_limited(key_hash):
        try:
            pg.close()
        except Exception:
            pass
        return None, (jsonify({"success": False, "error": "rate limit exceeded"}), 429)
    try:
        cur = pg.cursor()
        cur.execute(
            """SELECT k.id, k.tenant_id, t.status
               FROM api_keys k JOIN tenants t ON t.id = k.tenant_id
               WHERE k.key_hash = %s AND k.is_active""",
            (key_hash,),
        )
        row = cur.fetchone()
        if not row:
            pg.close()
            return None, (jsonify({"success": False, "error": "invalid API key"}), 401)
        if row[2] != "active":
            pg.close()
            return None, (
                jsonify(
                    {
                        "success": False,
                        "error": f"tenant status is '{row[2]}' — not approved for ingestion",
                    }
                ),
                403,
            )
        cur.execute("UPDATE api_keys SET last_used_at = NOW() WHERE id = %s", (row[0],))
        pg.commit()
        tenant_id = str(row[1])
        pg.close()
        return tenant_id, None
    except Exception as e:
        logger.error("api key resolution failed: %s", e)
        try:
            pg.close()
        except Exception:
            pass
        return None, (jsonify({"success": False, "error": "auth backend unavailable"}), 503)


def keyless_rejected():
    """P2.1 kill-switch for legacy keyless ingest (env REQUIRE_INGEST_KEYS).

    Returns an error response tuple when keyless ingest is disabled, else None.
    Flip on only AFTER every legitimate writer (the hub feed) sends a key.
    """
    import os

    if os.getenv("REQUIRE_INGEST_KEYS", "").lower() in ("1", "true", "yes"):
        return (
            jsonify({"success": False, "error": "API key required (Authorization: Bearer creed_sk_…)"}),
            401,
        )
    return None


def ingest_guard(description: str, metadata_str: str):
    """PII firewall + metadata cap for key-authenticated (external) ingest.

    Returns an (response, status) error tuple, or None when clean.
    """
    if len(metadata_str.encode("utf-8", errors="replace")) > METADATA_MAX_BYTES:
        return (
            jsonify({"success": False, "error": f"metadata exceeds {METADATA_MAX_BYTES} bytes"}),
            400,
        )
    text = f"{description or ''} {metadata_str or ''}"
    if _EMAIL_RE.search(text) or _PHONE_RE.search(text):
        return (
            jsonify(
                {
                    "success": False,
                    "error": (
                        "PII rejected: governance events must describe systems, "
                        "never data subjects (no emails or phone numbers)"
                    ),
                }
            ),
            400,
        )
    return None
