import re
from datetime import datetime, timezone
from flask import Blueprint, render_template, redirect, url_for, request, flash, session, current_app
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash, generate_password_hash
from ..extensions import db, limiter
from ..models import User, Assessment

auth_bp = Blueprint("auth", __name__)


# ── Landing page ──────────────────────────────────────────────────────────────

@auth_bp.route("/")
def landing():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))
    return render_template("landing.html")


# ── Admin login (password only) ───────────────────────────────────────────────

@auth_bp.route("/login", methods=["GET", "POST"])
@limiter.limit("5 per 15 minutes", methods=["POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))
    if request.method == "POST":
        password = request.form.get("password", "")
        username = request.form.get("username", "").strip()
        next_page = request.args.get("next")
        if username:
            # Customer / any-user login when username is explicitly supplied
            user = User.query.filter_by(username=username).first()
            if user and user.check_password(password):
                login_user(user)
                return redirect(next_page or url_for("dashboard.index"))
            flash("Invalid username or password.", "danger")
        else:
            # Admin-only login — password-only form, no username field
            admin = User.query.filter_by(role="admin").first()
            if admin and admin.check_password(password):
                login_user(admin)
                return redirect(next_page or url_for("dashboard.index"))
            flash("Incorrect password.", "danger")
    return render_template("login.html")


# ── Resume existing assessment (customer login) ───────────────────────────────

@auth_bp.route("/resume", methods=["GET", "POST"])
@limiter.limit("10 per 15 minutes", methods=["POST"])
def resume():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            next_page = request.args.get("next")
            return redirect(next_page or url_for("dashboard.index"))
        flash("Invalid name or password.", "danger")
    return render_template("resume.html")


# ── Customer self-registration / new assessment ───────────────────────────────

@auth_bp.route("/start", methods=["GET", "POST"])
@limiter.limit("10 per hour", methods=["POST"])
def start_assessment():
    if current_user.is_authenticated and current_user.role == "customer":
        return redirect(url_for("dashboard.index"))
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        org = request.form.get("org", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm", "")
        framework = request.form.get("framework", "dod_zt")

        errors = []
        if not name:
            errors.append("Name is required.")
        if not org:
            errors.append("Organisation name is required.")
        if len(password) < 12:
            errors.append("Password must be at least 12 characters.")
        if password != confirm:
            errors.append("Passwords do not match.")

        # Build a safe username from the name
        username = re.sub(r"[^a-zA-Z0-9_.-]", "_", name)[:80].lower()
        if User.query.filter_by(username=username).first():
            # Append a short suffix to make unique
            import secrets
            username = f"{username}_{secrets.token_hex(3)}"

        if not errors:
            assessment = Assessment(
                customer_org=org,
                framework=framework,
                variant="zt_only",
                status="draft",
            )
            db.session.add(assessment)
            db.session.flush()

            user = User(
                username=username,
                role="customer",
                assessment_id=assessment.id,
            )
            user.set_password(password)
            db.session.add(user)
            db.session.commit()

            login_user(user)
            flash(f"Welcome! Your assessment for {org} is ready.", "success")
            return redirect(url_for("assessment.workspace", assessment_id=assessment.id))

        for err in errors:
            flash(err, "danger")

    return render_template("start.html")


# ── Logout ────────────────────────────────────────────────────────────────────

@auth_bp.route("/logout")
@login_required
def logout():
    session.pop("admin_unlocked_at", None)
    logout_user()
    return redirect(url_for("auth.landing"))


# ── Admin unlock (second factor) ─────────────────────────────────────────────

@auth_bp.route("/admin/unlock", methods=["GET", "POST"])
@login_required
def admin_unlock():
    if request.method == "POST":
        password = request.form.get("admin_password", "")
        stored_hash = current_app.config.get("ADMIN_PASSWORD_HASH", "")
        if stored_hash and check_password_hash(stored_hash, password):
            session["admin_unlocked_at"] = datetime.now(timezone.utc).isoformat()
            flash("Admin mode unlocked.", "success")
            return redirect(request.args.get("next") or url_for("dashboard.index"))
        flash("Incorrect admin password.", "danger")
    return render_template("admin/unlock.html")


def is_admin_unlocked() -> bool:
    unlocked_at_str = session.get("admin_unlocked_at")
    if not unlocked_at_str:
        return False
    unlocked_at = datetime.fromisoformat(unlocked_at_str)
    timeout = current_app.config.get("ADMIN_SESSION_TIMEOUT", 3600)
    elapsed = (datetime.now(timezone.utc) - unlocked_at).total_seconds()
    if elapsed > timeout:
        session.pop("admin_unlocked_at", None)
        return False
    return True
