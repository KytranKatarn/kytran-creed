"""Self-serve org onboarding (task #3905, ADR-004 P2.4).

Flow: public application (/get-scored) → tenant created status='pending' +
email-verification token → applicant clicks /verify-email/<token> → institute
admin reviews identity (D1: verified real orgs only) in /admin/onboarding →
approve (status='active', first API key minted — shown ONCE to the admin to
forward securely) or reject (status='suspended').

Email is pluggable: when SMTP_* env vars are set the verification link is
emailed; otherwise it is surfaced in the admin queue for manual sending —
admin approval is the real gate either way, so onboarding works without SMTP.
"""

import hashlib
import logging
import os
import re
import secrets
import smtplib
import time
from collections import defaultdict, deque
from email.message import EmailMessage

from flask import Blueprint, jsonify, render_template, request

from kytran_creed.auth import admin_required
from kytran_creed.pg import get_pg
from kytran_creed.tenant_auth import generate_api_key

logger = logging.getLogger(__name__)
onboarding_bp = Blueprint("onboarding", __name__)

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,78}[a-z0-9]$")
_EMAIL_RE = re.compile(r"^[\w.+-]+@[\w-]+\.[\w.-]{2,}$")

# Signup abuse guard: 5 applications / hour / IP (per-worker, like public_routes).
APPLY_RATE_LIMIT = 5
APPLY_RATE_WINDOW = 3600
_apply_hits: dict[str, deque] = defaultdict(deque)


def _apply_rate_limited(ip: str) -> bool:
    now = time.time()
    hits = _apply_hits[ip]
    while hits and hits[0] < now - APPLY_RATE_WINDOW:
        hits.popleft()
    if len(hits) >= APPLY_RATE_LIMIT:
        return True
    hits.append(now)
    return False


def _send_verification_email(to_addr: str, org_name: str, verify_url: str) -> bool:
    """Send the verify link when SMTP is configured; False = not sent (manual)."""
    host = os.getenv("SMTP_HOST", "")
    if not host:
        logger.warning("onboarding: SMTP not configured — verify link for %s shown in admin queue", to_addr)
        return False
    try:
        msg = EmailMessage()
        msg["Subject"] = "Verify your email — C.R.E.E.D. transparency scoring application"
        msg["From"] = os.getenv("SMTP_FROM", "no-reply@creed-ai.org")
        msg["To"] = to_addr
        msg.set_content(
            f"Your organization '{org_name}' applied for C.R.E.E.D. transparency scoring.\n\n"
            f"Verify this contact address: {verify_url}\n\n"
            "After verification the Institute reviews your organization's identity "
            "(real, identifiable organizations only) and emails your ingest API key on approval.\n"
        )
        port = int(os.getenv("SMTP_PORT", "587"))
        with smtplib.SMTP(host, port, timeout=15) as s:
            s.starttls()
            user = os.getenv("SMTP_USER", "")
            if user:
                s.login(user, os.getenv("SMTP_PASSWORD", ""))
            s.send_message(msg)
        return True
    except Exception as e:
        logger.error("onboarding: verification email to %s failed: %s", to_addr, e)
        return False


@onboarding_bp.route("/get-scored")
def get_scored_page():
    return render_template("org_signup.html")


@onboarding_bp.route("/api/v1/onboarding/apply", methods=["POST"])
def apply():
    pg = get_pg()
    if not pg:
        return jsonify({"success": False, "error": "multi-tenant mode requires Postgres"}), 503
    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "?").split(",")[0].strip()
    if _apply_rate_limited(ip):
        pg.close()
        return jsonify({"success": False, "error": "rate limit exceeded — try again later"}), 429

    data = request.get_json(force=True, silent=True) or {}
    slug = (data.get("slug") or "").strip().lower()
    name = (data.get("name") or "").strip()
    website = (data.get("website") or "").strip()
    contact_email = (data.get("contact_email") or "").strip().lower()
    ai_description = (data.get("ai_description") or "").strip()
    if not _SLUG_RE.match(slug):
        pg.close()
        return jsonify({"success": False, "error": "slug must be 3-80 chars [a-z0-9-]"}), 400
    if not name or len(name) > 200:
        pg.close()
        return jsonify({"success": False, "error": "organization name required (<=200 chars)"}), 400
    if not _EMAIL_RE.match(contact_email):
        pg.close()
        return jsonify({"success": False, "error": "valid contact_email required"}), 400
    if not website.startswith(("http://", "https://")):
        pg.close()
        return jsonify({"success": False, "error": "website required (https://…) — D1: verified orgs only"}), 400
    if len(ai_description) < 20:
        pg.close()
        return jsonify({"success": False, "error": "describe your AI systems (>=20 chars)"}), 400

    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    try:
        cur = pg.cursor()
        cur.execute(
            """INSERT INTO tenants (slug, name, website, country, contact_email,
                                    status, listing, ai_description, verify_token)
               VALUES (%s, %s, %s, %s, %s, 'pending', 'preview', %s, %s)
               ON CONFLICT (slug) DO NOTHING RETURNING id""",
            (slug, name, website, (data.get("country") or "").strip() or None,
             contact_email, ai_description[:2000], token_hash),
        )
        row = cur.fetchone()
        pg.commit()
        pg.close()
        if not row:
            return jsonify({"success": False, "error": "that slug is already taken"}), 409
    except Exception as e:
        logger.error("onboarding apply failed: %s", e)
        try:
            pg.close()
        except Exception:
            pass
        return jsonify({"success": False, "error": "application failed"}), 500

    verify_url = request.host_url.rstrip("/") + "/verify-email/" + token
    emailed = _send_verification_email(contact_email, name, verify_url)
    if not emailed:
        # Only the hash is stored — without SMTP the operator must relay the
        # link by hand, so it has to be retrievable from the container logs.
        logger.info("onboarding: MANUAL verification link for %s <%s>: %s", slug, contact_email, verify_url)
    logger.info("onboarding: application %s (%s) — verification %s", slug, contact_email,
                "emailed" if emailed else "PENDING MANUAL SEND")
    return jsonify(
        {
            "success": True,
            "slug": slug,
            "status": "pending",
            "verification_emailed": emailed,
            "next": (
                "Check your inbox for the verification link."
                if emailed
                else "The Institute will contact you at the address provided to verify it."
            ),
        }
    ), 201


@onboarding_bp.route("/verify-email/<token>")
def verify_email(token):
    pg = get_pg()
    if not pg:
        return "Multi-tenant mode requires Postgres", 503
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    try:
        cur = pg.cursor()
        cur.execute(
            """UPDATE tenants SET email_verified = TRUE, verify_token = NULL
               WHERE verify_token = %s AND status = 'pending' RETURNING name""",
            (token_hash,),
        )
        row = cur.fetchone()
        pg.commit()
        pg.close()
    except Exception as e:
        logger.error("verify-email failed: %s", e)
        try:
            pg.close()
        except Exception:
            pass
        return "Verification failed", 500
    if not row:
        return "Invalid or already-used verification link.", 404
    return (
        f"<h2 style='font-family:sans-serif'>Email verified for {row[0]}.</h2>"
        "<p style='font-family:sans-serif'>The Institute now reviews your organization's "
        "identity and will email your ingest API key on approval.</p>"
    )


# ── Institute admin: approval queue ─────────────────────────────────────────

@onboarding_bp.route("/admin/onboarding")
@admin_required
def admin_onboarding_page():
    pg = get_pg()
    if not pg:
        return "Multi-tenant mode requires Postgres", 503
    try:
        cur = pg.cursor()
        cur.execute(
            """SELECT slug, name, website, country, contact_email, ai_description,
                      email_verified, verify_token, created_at
               FROM tenants WHERE status = 'pending' ORDER BY created_at"""
        )
        pending = [
            {
                "slug": r[0], "name": r[1], "website": r[2], "country": r[3],
                "contact_email": r[4], "ai_description": r[5],
                "email_verified": r[6],
                "needs_manual_verify_send": bool(r[7]) and not r[6],
                "applied": r[8].isoformat()[:16] if r[8] else "",
            }
            for r in cur.fetchall()
        ]
        pg.close()
        return render_template("admin_onboarding.html", pending=pending)
    except Exception as e:
        logger.error("admin onboarding queue failed: %s", e)
        try:
            pg.close()
        except Exception:
            pass
        return "Queue unavailable", 500


@onboarding_bp.route("/api/v1/orgs/<slug>/verify-link", methods=["POST"])
@admin_required
def regen_verify_link(slug):
    """Regenerate + return the email-verification link for a pending org.

    Only the token HASH is stored, and gunicorn does not surface app INFO logs,
    so when SMTP is unconfigured this is how the admin obtains the link to send
    manually.
    """
    pg = get_pg()
    if not pg:
        return jsonify({"success": False, "error": "multi-tenant mode requires Postgres"}), 503
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    try:
        cur = pg.cursor()
        cur.execute(
            """UPDATE tenants SET verify_token = %s
               WHERE slug = %s AND status = 'pending' AND NOT email_verified
               RETURNING contact_email""",
            (token_hash, slug),
        )
        row = cur.fetchone()
        pg.commit()
        pg.close()
        if not row:
            return jsonify({"success": False, "error": "no pending unverified org with that slug"}), 404
        return jsonify(
            {
                "success": True,
                "contact_email": row[0],
                "verify_url": request.host_url.rstrip("/") + "/verify-email/" + token,
            }
        )
    except Exception as e:
        logger.error("verify-link regen failed for %s: %s", slug, e)
        try:
            pg.close()
        except Exception:
            pass
        return jsonify({"success": False, "error": "regen failed"}), 500


@onboarding_bp.route("/api/v1/orgs/<slug>/approve", methods=["POST"])
@admin_required
def approve_org(slug):
    """Activate a pending org + mint its first ingest key (returned ONCE)."""
    pg = get_pg()
    if not pg:
        return jsonify({"success": False, "error": "multi-tenant mode requires Postgres"}), 503
    data = request.get_json(force=True, silent=True) or {}
    listing = data.get("listing", "preview")
    if listing not in ("preview", "public"):
        listing = "preview"
    try:
        cur = pg.cursor()
        cur.execute(
            """UPDATE tenants SET status = 'active', listing = %s
               WHERE slug = %s AND status = 'pending' RETURNING id, contact_email""",
            (listing, slug),
        )
        row = cur.fetchone()
        if not row:
            pg.close()
            return jsonify({"success": False, "error": "no pending org with that slug"}), 404
        plaintext, key_hash = generate_api_key()
        cur.execute(
            "INSERT INTO api_keys (tenant_id, key_hash, label) VALUES (%s, %s, %s)",
            (row[0], key_hash, "onboarding"),
        )
        pg.commit()
        pg.close()
        return jsonify(
            {
                "success": True,
                "slug": slug,
                "listing": listing,
                "api_key": plaintext,
                "contact_email": row[1],
                "note": "Forward this key securely to the org — it is shown exactly once.",
            }
        )
    except Exception as e:
        logger.error("approve org %s failed: %s", slug, e)
        try:
            pg.close()
        except Exception:
            pass
        return jsonify({"success": False, "error": "approve failed"}), 500


@onboarding_bp.route("/api/v1/orgs/<slug>/reject", methods=["POST"])
@admin_required
def reject_org(slug):
    pg = get_pg()
    if not pg:
        return jsonify({"success": False, "error": "multi-tenant mode requires Postgres"}), 503
    try:
        cur = pg.cursor()
        cur.execute(
            "UPDATE tenants SET status = 'suspended' WHERE slug = %s AND status = 'pending' RETURNING id",
            (slug,),
        )
        row = cur.fetchone()
        pg.commit()
        pg.close()
        if not row:
            return jsonify({"success": False, "error": "no pending org with that slug"}), 404
        return jsonify({"success": True, "slug": slug, "status": "suspended"})
    except Exception as e:
        logger.error("reject org %s failed: %s", slug, e)
        try:
            pg.close()
        except Exception:
            pass
        return jsonify({"success": False, "error": "reject failed"}), 500
