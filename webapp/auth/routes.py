"""auth/routes.py — Simple email/password login and user pages."""
from __future__ import annotations

import logging

from flask import (
    Blueprint, flash, redirect, render_template, request, url_for
)
from flask_login import current_user, login_required, login_user, logout_user

from auth.models import User
import database.users as users_db

logger = logging.getLogger(__name__)

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


# ── Registration ───────────────────────────────────────────────────────────

@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    """Register a new user account."""
    if current_user.is_authenticated:
        return redirect(url_for("index"))

    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        confirm = request.form.get("confirm_password") or ""
        name = (request.form.get("name") or "").strip()

        # Validation
        if not email or not password or not name:
            flash("All fields are required.", "danger")
            return redirect(url_for("auth.register"))

        if len(password) < 6:
            flash("Password must be at least 6 characters.", "danger")
            return redirect(url_for("auth.register"))

        if password != confirm:
            flash("Passwords do not match.", "danger")
            return redirect(url_for("auth.register"))

        # Check if email exists
        if users_db.get_user_by_email(email):
            flash("Email already registered.", "warning")
            return redirect(url_for("auth.login"))

        # Create user
        try:
            user = User(users_db.create_user(email, password, name))
            login_user(user, remember=True)
            logger.info("New user registered: %s", email)
            flash(f"Welcome, {name}! Your account has been created.", "success")
            return redirect(url_for("index"))
        except Exception as exc:
            logger.error("Failed to create user %s: %s", email, exc)
            flash("Error creating account. Please try again.", "danger")
            return redirect(url_for("auth.register"))

    return render_template("auth/register.html")


# ── Login ──────────────────────────────────────────────────────────────────

@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    """Log in with email and password."""
    if current_user.is_authenticated:
        return redirect(url_for("index"))

    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""

        if not email or not password:
            flash("Email and password are required.", "danger")
            return redirect(url_for("auth.login"))

        # Find user
        user_row = users_db.get_user_by_email(email)
        if not user_row:
            flash("Invalid email or password.", "warning")
            return redirect(url_for("auth.login"))

        # Verify password
        if not users_db.verify_password(user_row["password"], password):
            flash("Invalid email or password.", "warning")
            return redirect(url_for("auth.login"))

        # Log user in
        user = User(user_row)
        login_user(user, remember=True)
        logger.info("User signed in: %s", email)
        flash(f"Welcome back, {user.name}!", "success")

        next_url = request.args.get("next", "")
        if next_url and next_url.startswith("/"):
            return redirect(next_url)
        return redirect(url_for("index"))

    return render_template("auth/login.html")


# ── Logout ─────────────────────────────────────────────────────────────────

@auth_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    """Log out the current user."""
    email = current_user.email
    logout_user()
    logger.info("User signed out: %s", email)
    flash("You have been signed out.", "info")
    return redirect(url_for("index"))


# ── User pages ─────────────────────────────────────────────────────────────

@auth_bp.route("/profile")
@login_required
def profile():
    """View user profile with recent scans."""
    scan_count = users_db.get_user_scan_count(current_user.id)
    recent = users_db.get_user_scans(current_user.id, limit=5)
    return render_template("profile.html", scan_count=scan_count, recent=recent)


@auth_bp.route("/history")
@login_required
def history():
    """View full scan history."""
    scans = users_db.get_user_scans(current_user.id, limit=100)
    return render_template("history.html", scans=scans)


@auth_bp.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    """Account settings."""
    if request.method == "POST":
        flash("Settings saved.", "success")
        return redirect(url_for("auth.settings"))
    return render_template("settings.html")


@auth_bp.route("/delete", methods=["POST"])
@login_required
def delete_account():
    """Delete user account."""
    user_id = current_user.id
    email = current_user.email
    logout_user()
    users_db.delete_user(user_id)
    logger.info("Account deleted: %s", email)
    flash("Your account has been deleted.", "info")
    return redirect(url_for("index"))
