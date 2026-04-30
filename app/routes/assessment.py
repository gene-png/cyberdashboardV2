import io
import bleach
from datetime import datetime, timezone
from flask import Blueprint, render_template, redirect, url_for, request, flash, abort, send_file
from flask_login import login_required, current_user
from ..extensions import db
from ..models import Assessment, Response, ToolInventory, AuditLog, GapFinding, SensitiveTerm
from ..services.framework_loader import load_framework
from ..services.excel_service import build_customer_excel
from .auth import is_admin_unlocked

assessment_bp = Blueprint("assessment", __name__)

_ALLOWED_TAGS: list = []  # bleach strips all html, keep plain text only


def _sanitize(text: str | None) -> str:
    if not text:
        return ""
    return bleach.clean(text, tags=_ALLOWED_TAGS, strip=True)


def _get_assessment_or_403(assessment_id: str) -> Assessment:
    assessment = db.session.get(Assessment, assessment_id)
    if not assessment:
        abort(404)
    if current_user.role == "customer" and current_user.assessment_id != assessment_id:
        abort(403)
    return assessment


def _log_audit(assessment_id, action, target_type, target_id, before=None, after=None):
    log = AuditLog(
        assessment_id=assessment_id,
        user_id=current_user.id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        before_value=str(before) if before is not None else None,
        after_value=str(after) if after is not None else None,
    )
    db.session.add(log)


@assessment_bp.route("/assessments/<assessment_id>")
@login_required
def workspace(assessment_id):
    assessment = _get_assessment_or_403(assessment_id)

    # Resume to last-saved step unless the user explicitly wants the overview
    if assessment.current_step and not request.args.get("overview"):
        step = assessment.current_step
        if step.startswith("pillar_"):
            pillar_id = step[len("pillar_"):]
            return redirect(url_for("assessment.pillar", assessment_id=assessment_id, pillar_id=pillar_id))

    framework = load_framework(assessment.framework)
    responses = {r.activity_id: r for r in assessment.responses}
    user_terms = (
        SensitiveTerm.query
        .filter_by(assessment_id=assessment_id, source="user_added", is_active=True)
        .order_by(SensitiveTerm.term)
        .all()
    )
    return render_template(
        "assessment/workspace.html",
        assessment=assessment,
        framework=framework,
        responses=responses,
        user_terms=user_terms,
        admin_unlocked=is_admin_unlocked(),
    )


@assessment_bp.route("/assessments/<assessment_id>/inventory", methods=["GET", "POST"])
@login_required
def inventory(assessment_id):
    assessment = _get_assessment_or_403(assessment_id)
    if request.method == "POST":
        if not assessment.is_editable_by_customer and not is_admin_unlocked():
            flash("Assessment is locked.", "warning")
            return redirect(url_for("assessment.inventory", assessment_id=assessment_id))

        name = _sanitize(request.form.get("name", ""))
        vendor = _sanitize(request.form.get("vendor", ""))
        category = _sanitize(request.form.get("category", ""))
        notes = _sanitize(request.form.get("notes", ""))
        if name:
            tool = ToolInventory(
                assessment_id=assessment_id,
                name=name, vendor=vendor, category=category, notes=notes
            )
            db.session.add(tool)
            if assessment.status == "draft":
                assessment.status = "in_progress"
            db.session.commit()
            flash("Tool added.", "success")
        return redirect(url_for("assessment.inventory", assessment_id=assessment_id))

    return render_template(
        "assessment/inventory.html",
        assessment=assessment,
        tools=assessment.tool_inventory,
        admin_unlocked=is_admin_unlocked(),
    )


@assessment_bp.route("/assessments/<assessment_id>/inventory/<tool_id>/delete", methods=["POST"])
@login_required
def delete_tool(assessment_id, tool_id):
    assessment = _get_assessment_or_403(assessment_id)
    if not assessment.is_editable_by_customer and not is_admin_unlocked():
        abort(403)
    tool = db.session.get(ToolInventory, tool_id)
    if not tool or tool.assessment_id != assessment_id:
        abort(404)
    db.session.delete(tool)
    db.session.commit()
    flash("Tool removed.", "success")
    return redirect(url_for("assessment.inventory", assessment_id=assessment_id))


@assessment_bp.route("/assessments/<assessment_id>/pillar/<pillar_id>", methods=["GET", "POST"])
@login_required
def pillar(assessment_id, pillar_id):
    assessment = _get_assessment_or_403(assessment_id)
    framework = load_framework(assessment.framework)

    pillar_data = next((p for p in framework["pillars"] if p["id"] == pillar_id), None)
    if not pillar_data:
        abort(404)

    responses = {r.activity_id: r for r in assessment.responses}
    can_edit = assessment.is_editable_by_customer or is_admin_unlocked()

    if request.method == "POST":
        if not can_edit:
            flash("Assessment is locked.", "warning")
            return redirect(url_for("assessment.pillar", assessment_id=assessment_id, pillar_id=pillar_id))

        for activity in pillar_data["activities"]:
            aid = activity["id"]
            current_val = request.form.get(f"current_{aid}", "")
            target_val = request.form.get(f"target_{aid}", "")
            notes = _sanitize(request.form.get(f"notes_{aid}", ""))

            resp = responses.get(aid)
            before = None
            if resp:
                before = f"{resp.current_state_value}|{resp.target_state_value}"
                resp.current_state_value = current_val or None
                resp.target_state_value = target_val or None
                resp.evidence_notes = notes
                resp.last_edited_by = current_user.id
                # Mark related gap finding stale if it exists
                finding = GapFinding.query.filter_by(assessment_id=assessment_id, activity_id=aid).first()
                if finding:
                    finding.is_stale = True
            else:
                resp = Response(
                    assessment_id=assessment_id,
                    pillar=pillar_id,
                    activity_id=aid,
                    current_state_value=current_val or None,
                    target_state_value=target_val or None,
                    evidence_notes=notes,
                    last_edited_by=current_user.id,
                )
                db.session.add(resp)

            after = f"{current_val}|{target_val}"
            _log_audit(assessment_id, "update" if before else "create", "response", aid, before, after)

        if assessment.status == "draft":
            assessment.status = "in_progress"
        assessment.current_step = f"pillar_{pillar_id}"
        db.session.commit()
        flash("Responses saved.", "success")
        return redirect(url_for("assessment.pillar", assessment_id=assessment_id, pillar_id=pillar_id))

    return render_template(
        "assessment/pillar.html",
        assessment=assessment,
        pillar=pillar_data,
        framework=framework,
        responses=responses,
        can_edit=can_edit,
        admin_unlocked=is_admin_unlocked(),
    )


@assessment_bp.route("/assessments/<assessment_id>/submit", methods=["GET", "POST"])
@login_required
def submit(assessment_id):
    assessment = _get_assessment_or_403(assessment_id)

    if request.method == "POST":
        if assessment.status not in ("draft", "in_progress"):
            flash("Assessment cannot be submitted in its current state.", "warning")
        else:
            assessment.status = "awaiting_review"
            _log_audit(assessment_id, "submit", "assessment", assessment_id)
            db.session.commit()
            flash("Assessment submitted for review.", "success")
        return redirect(url_for("assessment.workspace", assessment_id=assessment_id))

    framework = load_framework(assessment.framework)
    responses = {r.activity_id: r for r in assessment.responses}
    total_activities = sum(len(p["activities"]) for p in framework["pillars"])
    answered = sum(1 for r in assessment.responses if r.current_state_value and r.target_state_value)
    return render_template(
        "assessment/submit.html",
        assessment=assessment,
        total_activities=total_activities,
        answered=answered,
        admin_unlocked=is_admin_unlocked(),
    )


@assessment_bp.route("/assessments/<assessment_id>/terms", methods=["POST"])
@login_required
def add_sensitive_terms(assessment_id):
    assessment = _get_assessment_or_403(assessment_id)
    if not assessment.is_editable_by_customer and not is_admin_unlocked():
        flash("Assessment is locked.", "warning")
        return redirect(url_for("assessment.workspace", assessment_id=assessment_id, overview=1))

    raw_block = request.form.get("terms", "")
    added = 0
    for raw in raw_block.splitlines():
        term = _sanitize(raw).strip()
        if not term:
            continue
        already = SensitiveTerm.query.filter_by(
            assessment_id=assessment_id, term=term, is_active=True
        ).first()
        if already:
            continue
        count = SensitiveTerm.query.filter_by(
            assessment_id=assessment_id, source="user_added"
        ).count()
        token = f"[CUSTOM_{count + 1}]"
        st = SensitiveTerm(
            assessment_id=assessment_id,
            term=term,
            replacement_token=token,
            source="user_added",
            is_active=True,
        )
        db.session.add(st)
        _log_audit(assessment_id, "add_sensitive_term", "sensitive_term", token, after=term)
        added += 1

    if added:
        db.session.commit()
        flash(f"{added} sensitive term(s) added.", "success")
    else:
        flash("No new terms to add.", "info")

    return redirect(url_for("assessment.workspace", assessment_id=assessment_id, overview=1))


@assessment_bp.route("/assessments/<assessment_id>/report")
@login_required
def final_report(assessment_id):
    """Customer-accessible download of their Excel report after finalization."""
    assessment = _get_assessment_or_403(assessment_id)
    if assessment.status != "finalized":
        flash("The final report is only available after the assessment has been finalized.", "warning")
        return redirect(url_for("assessment.workspace", assessment_id=assessment_id))

    xlsx_bytes = build_customer_excel(assessment)
    date_str = (assessment.finalized_at or datetime.now(timezone.utc)).strftime("%Y-%m-%d")
    filename = f"{assessment.customer_org.replace(' ', '_')}_{date_str}_report.xlsx"
    return send_file(
        io.BytesIO(xlsx_bytes),
        as_attachment=True,
        download_name=filename,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
