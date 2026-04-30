import os
import logging
from flask import Flask, redirect, request
from .extensions import db, login_manager, csrf, limiter
from .config import Config

logger = logging.getLogger(__name__)


def _configure_logging(app: Flask) -> None:
    if not app.debug and not app.testing:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(name)s %(message)s",
        )
    else:
        logging.basicConfig(level=logging.DEBUG)


def create_app(config_class=Config):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_class)

    os.makedirs(app.instance_path, exist_ok=True)
    _configure_logging(app)

    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)

    from .routes.auth import auth_bp
    from .routes.dashboard import dashboard_bp
    from .routes.assessment import assessment_bp
    from .routes.admin import admin_bp
    from .routes.htmx import htmx_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(assessment_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(htmx_bp)

    # Exempt HTMX auto-save from CSRF (uses session auth + same-origin)
    csrf.exempt(htmx_bp)

    # HTTPS force-redirect via X-Forwarded-Proto (Azure App Service terminates TLS)
    if app.config.get("FORCE_HTTPS"):
        @app.before_request
        def _redirect_http_to_https():
            if request.headers.get("X-Forwarded-Proto", "https") == "http":
                return redirect(request.url.replace("http://", "https://", 1), code=301)

    with app.app_context():
        db.create_all()
        _seed_admin_user(app)

    return app


def _seed_admin_user(app: Flask) -> None:
    """Create the initial admin user on first run if none exists."""
    from .models import User
    pw_hash = app.config.get("ADMIN_PASSWORD_HASH", "")
    if not pw_hash:
        return
    if User.query.filter_by(role="admin").first():
        return
    username = app.config.get("ADMIN_USERNAME", "admin")
    admin = User(username=username, role="admin", password_hash=pw_hash)
    db.session.add(admin)
    db.session.commit()
    logger.info("Created initial admin user '%s'", username)
