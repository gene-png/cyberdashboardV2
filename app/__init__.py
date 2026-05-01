import os
import re
import html
import logging
from flask import Flask, redirect, request
from .extensions import db, login_manager, csrf, limiter
from .config import Config


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

    @app.template_filter("render_md")
    def render_md(text):
        """Convert the AI's basic markdown (bold, numbered lists, newlines) to safe HTML."""
        if not text:
            return ""
        escaped = html.escape(text)
        # bold
        escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
        # paragraph breaks
        parts = escaped.split("\n\n")
        parts = [p.replace("\n", "<br>") for p in parts]
        return "<p>" + "</p><p>".join(parts) + "</p>"

    with app.app_context():
        db.create_all()

    return app
