"""PhishGuard — Flask application entry point."""
from __future__ import annotations

import logging
import os
import secrets
import sys
from datetime import timedelta, datetime

from flask import Flask, abort, jsonify, redirect, render_template, request, session, url_for
from flask_login import LoginManager, current_user, login_required

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv is optional; env vars may be set by the shell

from api.scan import scan_bp
from api.batch import batch_bp
from api.circuit import circuit_bp
from auth.routes import auth_bp
from auth.models import User
import models.loader as loader
import database.db as db
import database.users as users_db

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024  # 5 MB upload cap
app.config["SECRET_KEY"] = os.environ.get(
    "SECRET_KEY", "dev-key-change-before-any-deployment"
)

# Session & cookie security
_is_production = os.environ.get("FLASK_ENV") == "production"
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = _is_production  # True only over HTTPS
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=30)
app.config["REMEMBER_COOKIE_HTTPONLY"] = True
app.config["REMEMBER_COOKIE_SECURE"] = _is_production
app.config["REMEMBER_COOKIE_DURATION"] = timedelta(days=30)
app.config["REMEMBER_COOKIE_SAMESITE"] = "Lax"

# ---------------------------------------------------------------------------
# Flask-Login
# ---------------------------------------------------------------------------
login_manager = LoginManager(app)
login_manager.login_view = "auth.login"           # type: ignore[assignment]
login_manager.login_message = "Please sign in to access this page."
login_manager.login_message_category = "warning"


@login_manager.user_loader
def load_user(user_id: str) -> "User | None":
    return User.get(int(user_id))


# ---------------------------------------------------------------------------
# OAuth disabled — using simple email/password authentication
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Blueprints
# ---------------------------------------------------------------------------
app.register_blueprint(scan_bp)
app.register_blueprint(batch_bp)
app.register_blueprint(circuit_bp)
app.register_blueprint(auth_bp)

# ---------------------------------------------------------------------------
# CSRF — session-token approach for all HTML form POSTs
# API endpoints (/api/*) use JSON bodies and are exempt.
# ---------------------------------------------------------------------------
def _csrf_token() -> str:
    """Return (and lazily create) the per-session CSRF token."""
    if "_csrf_token" not in session:
        session["_csrf_token"] = secrets.token_hex(32)
    return session["_csrf_token"]


app.jinja_env.globals["csrf_token"] = _csrf_token


@app.template_filter("format_date")
def format_date_filter(date_str: str) -> str:
    """Format ISO datetime string to readable month and year."""
    if not date_str:
        return "Recently"
    try:
        dt = datetime.fromisoformat(date_str)
        return dt.strftime("%B %Y")
    except (ValueError, AttributeError):
        return "Recently"


@app.before_request
def enforce_csrf() -> None:
    if request.method != "POST":
        return
    if request.path.startswith("/api/"):
        return  # JSON API; no form CSRF needed
    token = session.get("_csrf_token", "")
    form_token = request.form.get("csrf_token", "")
    # Require both tokens to be non-empty AND equal — empty == empty must fail.
    if not token or not form_token or not secrets.compare_digest(token, form_token):
        abort(403)


# ---------------------------------------------------------------------------
# CORS — allow only browser extensions and localhost dev origins.
# Wildcard "*" is intentionally avoided on data-modifying endpoints.
# ---------------------------------------------------------------------------
_ALLOWED_ORIGINS = {"http://localhost:5000", "http://127.0.0.1:5000"}


@app.after_request
def add_headers(response):
    origin = request.headers.get("Origin", "")
    if (
        origin.startswith("chrome-extension://")
        or origin.startswith("moz-extension://")
        or origin in _ALLOWED_ORIGINS
    ):
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Vary"] = "Origin"

    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"

    if request.method == "OPTIONS":
        response.status_code = 200

    # Security headers
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' https://cdn.jsdelivr.net; "
        "style-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'; "
        # Google profile pictures are served from lh3.googleusercontent.com
        "img-src 'self' data: https://lh3.googleusercontent.com https://*.googleusercontent.com; "
        "connect-src 'self';"
    )
    return response


# ---------------------------------------------------------------------------
# Error handlers
# ---------------------------------------------------------------------------
@app.errorhandler(400)
def bad_request(e):
    return jsonify({"error": "Bad request"}), 400


@app.errorhandler(403)
def forbidden(e):
    return render_template("errors/403.html"), 403


@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Not found"}), 404


@app.errorhandler(413)
def request_too_large(e):
    return jsonify({"error": "File too large — maximum 5 MB allowed"}), 413


@app.errorhandler(500)
def internal_error(e):
    logger.exception("Unhandled internal server error")
    return jsonify({"error": "Internal server error"}), 500


# ---------------------------------------------------------------------------
# Page routes
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    return render_template("landing.html")


@app.route("/analyser")
@login_required
def analyser():
    return render_template("index.html")


@app.route("/batch")
@login_required
def batch():
    return render_template("batch.html")


@app.route("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html")


@app.route("/visualizer")
@login_required
def visualizer():
    return render_template("visualizer.html")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    with app.app_context():
        db.init_db()
        users_db.init_user_tables()
        logger.info("Database initialised at %s", db.DB_PATH)
        try:
            loader.initialize()
        except FileNotFoundError as exc:
            logger.critical("Dataset not found — cannot start: %s", exc)
            sys.exit(1)
        except Exception as exc:
            logger.critical("Model initialisation failed: %s", exc, exc_info=True)
            sys.exit(1)
    app.run(
        host="127.0.0.1",
        port=5000,
        debug=False,
        threaded=True,
    )
