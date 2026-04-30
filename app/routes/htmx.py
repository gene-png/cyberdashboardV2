"""
HTMX partial endpoints — auto-save for individual activity responses.

Each endpoint returns a small HTML fragment that replaces a save-indicator
element in the page. No full page reload required.
"""
import bleach
from datetime import datetime, timezone
from flask import Blueprint, request, current_app, abort
from flask_login import login_required, current_user
from ..extensions import db
from ..models import Assessment, Response, GapFinding, AuditLog
from .auth import is_admin_unlocked

htmx_bp = Blueprint("htmx", __name__, url_prefix="/htmx")

_ALLOWED_TAGS: list = []


def _sanitize(text: str | None) -> str:
    if not text:
        return ""
    return bleach.clean(text, tags=_ALLOWED_TAGS, strip=True)


@htmx_bp.route("/assessments/<assessment_id>/response/<path:activity_id>", methods=["POST"])
@login_required
def save_response(assessment_id: str, activity_id: str):
    """Auto-save a single activity response. Returns an inline status fragment."""
    assessment = db.session.get(Assessment, assessment_id)
    if not assessment:
        abort(404)

    # Access control
    if current_user.role == "customer" and current_user.assessment_id != assessment_id:
        return _error_fragment("Access denied.")

    can_edit = assessment.is_editable_by_customer or is_admin_unlocked()
    if not can_edit:
        return _error_fragment("Assessment is locked.")

    current_val = request.form.get("current", "") or None
    target_val = request.form.get("target", "") or None
    notes = _sanitize(request.form.get("notes", "")) or None

    # Derive pillar from activity_id (e.g. "dod_zt.user.1.1" → "user")
    parts = activity_id.split(".")
    pillar = parts[2] if len(parts) >= 3 else "unknown"

    resp = Response.query.filter_by(
        assessment_id=assessment_id, activity_id=activity_id
    ).first()

    before = None
    if resp:
        before = f"{resp.current_state_value}|{resp.target_state_value}"
        resp.current_state_value = current_val
        resp.target_state_value = target_val
        resp.evidence_notes = notes
        resp.last_edited_by = current_user.id
    else:
        resp = Response(
            assessment_id=assessment_id,
            pillar=pillar,
            activity_id=activity_id,
            current_state_value=current_val,
            target_state_value=target_val,
            evidence_notes=notes,
            last_edited_by=current_user.id,
        )
        db.session.add(resp)

    # Mark related gap finding stale (any edit invalidates previous AI guidance)
    stale_finding = GapFinding.query.filter_by(
        assessment_id=assessment_id, activity_id=activity_id
    ).first()
    if stale_finding:
        stale_finding.is_stale = True

    after = f"{current_val}|{target_val}"
    audit = AuditLog(
        assessment_id=assessment_id,
        user_id=current_user.id,
        action="update" if before else "create",
        target_type="response",
        target_id=activity_id,
        before_value=before,
        after_value=after,
    )
    db.session.add(audit)

    if assessment.status == "draft":
        assessment.status = "in_progress"

    db.session.commit()
    return _saved_fragment()


def _saved_fragment() -> str:
    return '<span class="save-indicator save-ok">Saved</span>'


def _error_fragment(msg: str) -> str:
    return f'<span class="save-indicator save-err">{bleach.clean(msg)}</span>'
