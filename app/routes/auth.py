from datetime import datetime, timezone
from flask import Blueprint, render_template, redirect, url_for, request, flash, session, current_app
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash
from ..extensions import db, limiter
from ..models import User

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["GET", "POST"])
@limiter.limit("5 per 15 minutes", methods=["POST"])
def login():
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
        flash("Invalid username or password.", "danger")
    return render_template("login.html")


@auth_bp.route("/logout")
@login_required
def logout():
    session.pop("admin_unlocked_at", None)
    logout_user()
    return redirect(url_for("auth.login"))


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
    timeout = current_app.config.get("ADMIN_SESSION_TIMEOUT", 900)
    elapsed = (datetime.now(timezone.utc) - unlocked_at).total_seconds()
    if elapsed > timeout:
        session.pop("admin_unlocked_at", None)
        return False
    return True
