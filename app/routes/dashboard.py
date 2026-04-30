from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_required, current_user
from ..extensions import db
from ..models import Assessment, User
from .auth import is_admin_unlocked

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/")
@login_required
def index():
    if current_user.role == "customer":
        assessment = db.session.get(Assessment, current_user.assessment_id)
        if assessment:
            return redirect(url_for("assessment.workspace", assessment_id=assessment.id))
        return render_template("dashboard.html", assessments=[], admin_unlocked=False)

    # admin view — show all assessments
    assessments = Assessment.query.order_by(Assessment.created_at.desc()).all()
    return render_template(
        "dashboard.html",
        assessments=assessments,
        admin_unlocked=is_admin_unlocked(),
    )


@dashboard_bp.route("/assessments/new", methods=["GET", "POST"])
@login_required
def new_assessment():
    if not is_admin_unlocked():
        return redirect(url_for("auth.admin_unlock", next=request.url))

    if request.method == "POST":
        customer_org = request.form.get("customer_org", "").strip()
        framework = request.form.get("framework", "dod_zt")
        variant = request.form.get("variant", "zt_only")
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if not customer_org or not username or not password:
            flash("All fields are required.", "danger")
            return render_template("new_assessment.html")

        if User.query.filter_by(username=username).first():
            flash("Username already taken.", "danger")
            return render_template("new_assessment.html")

        assessment = Assessment(
            customer_org=customer_org,
            framework=framework,
            variant=variant,
            status="draft",
        )
        db.session.add(assessment)
        db.session.flush()

        customer_user = User(
            username=username,
            role="customer",
            assessment_id=assessment.id,
        )
        customer_user.set_password(password)
        db.session.add(customer_user)
        db.session.commit()

        flash(f"Assessment created for {customer_org}.", "success")
        return redirect(url_for("dashboard.index"))

    return render_template("new_assessment.html")
