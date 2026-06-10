"""Algorithmic Impact Assessment (AIA) routes — ISO 42001 Annex A.5 compliance."""
import json
import logging
from datetime import datetime, timezone

from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required

logger = logging.getLogger(__name__)
aia_bp = Blueprint("aia", __name__, url_prefix="/aia")

AIA_QUESTIONS = [
    {"id": "name", "label": "AI System Name", "type": "text", "required": True, "help": "The canonical name of this AI system or agent."},
    {"id": "purpose", "label": "Purpose and Use Case", "type": "textarea", "required": True, "help": "What does this system do? What problem does it solve?"},
    {"id": "affected_parties", "label": "Affected Parties", "type": "textarea", "required": True, "help": "Who are the people, groups, or organisations affected by this system's outputs?"},
    {"id": "decision_type", "label": "Decision Type", "type": "select", "required": True, "help": "How autonomous are decisions made by or with this system?",
     "options": [("automated", "Fully Automated — no human in the loop"), ("augmented", "Human-Augmented — AI proposes, human approves"), ("advisory", "Advisory Only — human retains full decision authority")]},
    {"id": "human_oversight", "label": "Human Oversight Mechanism", "type": "textarea", "required": True, "help": "Describe how humans monitor, review, or override this system."},
    {"id": "risk_tier", "label": "Risk Tier", "type": "select", "required": True, "help": "Aligned to EU AI Act risk tiers.",
     "options": [("minimal", "Minimal — no significant impact on individuals"), ("limited", "Limited — low-stakes, easily reversible outcomes"), ("high", "High — significant impact on rights, health, safety, or livelihood"), ("unacceptable", "Unacceptable — prohibited under applicable regulation")]},
    {"id": "data_sources", "label": "Data Sources", "type": "textarea", "required": False, "help": "What data does this system use?"},
    {"id": "known_limitations", "label": "Known Limitations and Failure Modes", "type": "textarea", "required": False, "help": "What are the known weaknesses, biases, or edge cases?"},
    {"id": "mitigation_measures", "label": "Mitigation Measures", "type": "textarea", "required": False, "help": "What controls, safeguards, or monitoring are in place?"},
    {"id": "review_cadence", "label": "Review Cadence", "type": "text", "required": False, "help": "How often will this assessment be reviewed? (e.g. 'Quarterly')"},
]

REQUIRED_FIELDS = {"name", "purpose", "affected_parties", "human_oversight"}


def _get_pg():
    try:
        from kytran_creed.pg import get_pg
        return get_pg()
    except Exception:
        return None


def _get_db():
    from kytran_creed.db import get_db
    return get_db()


def _list_assessments():
    pg = _get_pg()
    if pg:
        try:
            cur = pg.cursor()
            cur.execute("SELECT id, name, risk_tier, decision_type, status, created_at FROM aia_assessments ORDER BY created_at DESC")
            cols = [d[0] for d in cur.description]
            rows = [dict(zip(cols, r)) for r in cur.fetchall()]
            pg.close()
            return rows
        except Exception as exc:
            logger.error("PG list aia: %s", exc)
            try:
                pg.close()
            except Exception:
                pass
    conn = _get_db()
    try:
        cur = conn.execute("SELECT id, name, risk_tier, decision_type, status, created_at FROM aia_assessments ORDER BY created_at DESC")
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def _get_assessment(aia_id):
    pg = _get_pg()
    if pg:
        try:
            cur = pg.cursor()
            cur.execute("SELECT * FROM aia_assessments WHERE id = %s", (aia_id,))
            cols = [d[0] for d in cur.description]
            row = cur.fetchone()
            pg.close()
            return dict(zip(cols, row)) if row else None
        except Exception as exc:
            logger.error("PG get aia: %s", exc)
            try:
                pg.close()
            except Exception:
                pass
    conn = _get_db()
    try:
        cur = conn.execute("SELECT * FROM aia_assessments WHERE id = ?", (aia_id,))
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def _save_assessment(data, aia_id=None):
    answers = json.dumps(data.get("answers", {}))
    fields = (
        data.get("name", ""),
        data.get("purpose", ""),
        data.get("affected_parties", ""),
        data.get("decision_type", "advisory"),
        data.get("human_oversight", ""),
        data.get("risk_tier", "limited"),
        data.get("data_sources", "") or "",
        data.get("known_limitations", "") or "",
        data.get("mitigation_measures", "") or "",
        data.get("review_cadence", "") or "",
        answers,
        data.get("status", "draft"),
        data.get("created_by", "admin"),
    )
    pg = _get_pg()
    if pg:
        try:
            cur = pg.cursor()
            if aia_id:
                cur.execute(
                    "UPDATE aia_assessments SET name=%s, purpose=%s, affected_parties=%s, decision_type=%s, human_oversight=%s, risk_tier=%s, data_sources=%s, known_limitations=%s, mitigation_measures=%s, review_cadence=%s, answers_json=%s, status=%s, created_by=%s, updated_at=NOW() WHERE id=%s",
                    fields + (aia_id,),
                )
                new_id = aia_id
            else:
                cur.execute(
                    "INSERT INTO aia_assessments (name, purpose, affected_parties, decision_type, human_oversight, risk_tier, data_sources, known_limitations, mitigation_measures, review_cadence, answers_json, status, created_by) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                    fields,
                )
                new_id = cur.fetchone()[0]
            pg.commit()
            pg.close()
            return new_id
        except Exception as exc:
            logger.error("PG save aia: %s", exc)
            try:
                pg.close()
            except Exception:
                pass
    conn = _get_db()
    try:
        if aia_id:
            conn.execute(
                "UPDATE aia_assessments SET name=?, purpose=?, affected_parties=?, decision_type=?, human_oversight=?, risk_tier=?, data_sources=?, known_limitations=?, mitigation_measures=?, review_cadence=?, answers_json=?, status=?, created_by=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                fields + (aia_id,),
            )
            conn.commit()
            return aia_id
        cur = conn.execute(
            "INSERT INTO aia_assessments (name, purpose, affected_parties, decision_type, human_oversight, risk_tier, data_sources, known_limitations, mitigation_measures, review_cadence, answers_json, status, created_by) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            fields,
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


@aia_bp.route("/")
@login_required
def list_aias():
    assessments = _list_assessments()
    return render_template("aia_list.html", assessments=assessments)


@aia_bp.route("/new", methods=["GET", "POST"])
@login_required
def new_aia():
    if request.method == "POST":
        data = {q["id"]: request.form.get(q["id"], "").strip() for q in AIA_QUESTIONS}
        data["status"] = "draft"
        data["created_by"] = getattr(current_user, "username", "admin") if current_user.is_authenticated else "admin"
        missing = [q["label"] for q in AIA_QUESTIONS if q["required"] and not data.get(q["id"])]
        if missing:
            flash(f"Required: {', '.join(missing)}", "error")
            return render_template("aia_form.html", questions=AIA_QUESTIONS, data=data, edit=False)
        aia_id = _save_assessment(data)
        flash(f"Assessment created (ID {aia_id}).", "success")
        return redirect(url_for("aia.view_aia", aia_id=aia_id))
    return render_template("aia_form.html", questions=AIA_QUESTIONS, data={}, edit=False)


@aia_bp.route("/<int:aia_id>")
@login_required
def view_aia(aia_id):
    assessment = _get_assessment(aia_id)
    if not assessment:
        flash("Assessment not found.", "error")
        return redirect(url_for("aia.list_aias"))
    if isinstance(assessment.get("answers_json"), str):
        try:
            assessment["answers_json"] = json.loads(assessment["answers_json"])
        except Exception:
            assessment["answers_json"] = {}
    return render_template("aia_report.html", assessment=assessment, questions=AIA_QUESTIONS)


@aia_bp.route("/<int:aia_id>/edit", methods=["GET", "POST"])
@login_required
def edit_aia(aia_id):
    assessment = _get_assessment(aia_id)
    if not assessment:
        flash("Assessment not found.", "error")
        return redirect(url_for("aia.list_aias"))
    if request.method == "POST":
        data = {q["id"]: request.form.get(q["id"], "").strip() for q in AIA_QUESTIONS}
        data["status"] = request.form.get("status", assessment.get("status", "draft"))
        data["created_by"] = assessment.get("created_by", "admin")
        _save_assessment(data, aia_id=aia_id)
        flash("Assessment updated.", "success")
        return redirect(url_for("aia.view_aia", aia_id=aia_id))
    return render_template("aia_form.html", questions=AIA_QUESTIONS, data=assessment, edit=True, aia_id=aia_id)


@aia_bp.route("/<int:aia_id>/publish", methods=["POST"])
@login_required
def publish_aia(aia_id):
    assessment = _get_assessment(aia_id)
    if not assessment:
        return jsonify({"error": "not found"}), 404
    assessment["status"] = "published"
    _save_assessment(assessment, aia_id=aia_id)
    return jsonify({"success": True, "status": "published"})
