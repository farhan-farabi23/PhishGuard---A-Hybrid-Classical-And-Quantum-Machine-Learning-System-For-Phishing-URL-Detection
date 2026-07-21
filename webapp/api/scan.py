"""api/scan.py — Blueprint for single-URL scan, health, stats, and history endpoints."""

import logging
import time

from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required

import models.loader as loader
import database.db as db
from api.helpers import safe_int, MAX_URL_LENGTH

logger = logging.getLogger(__name__)
scan_bp = Blueprint("scan", __name__)


@scan_bp.route("/api/health")
def api_health():
    return jsonify({"status": "ok", "initialized": loader.is_initialized()})


@scan_bp.route("/api/auth-status")
def api_auth_status():
    """Check if the current user is authenticated.

    Returns: { "authenticated": bool, "email": str | null }
    """
    if current_user.is_authenticated:
        return jsonify({"authenticated": True, "email": current_user.email})
    return jsonify({"authenticated": False, "email": None})


@scan_bp.route("/api/scan", methods=["POST"])
@login_required
def api_scan():
    """Accept a URL, run all models, return JSON results.

    Request body (JSON): {"url": "...", "include_quantum": true/false}
    Returns: full predict_all dict + scan metadata.
    """
    body = request.get_json(silent=True) or {}
    url = (body.get("url") or "").strip()
    include_quantum = bool(body.get("include_quantum", True))

    if not url:
        return jsonify({"error": "url is required"}), 400
    if len(url) > MAX_URL_LENGTH:
        return jsonify({"error": f"URL too long (max {MAX_URL_LENGTH} characters)"}), 400

    t_start = time.monotonic()
    try:
        results = loader.predict_all(url, include_quantum=include_quantum)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 503

    elapsed = round((time.monotonic() - t_start) * 1000)

    verdict = results["ensemble"]["verdict"]
    confidence = results["ensemble"]["confidence"]

    user_id = current_user.id if current_user.is_authenticated else None
    try:
        db.save_scan(url, verdict, confidence, results, user_id=user_id)
    except Exception:
        # A DB write failure must not turn a successful scan into a 500 error.
        logger.exception("Failed to persist scan for %s", url)

    results["meta"] = {
        "url":             url,
        "total_time_ms":   elapsed,
        "include_quantum": include_quantum,
    }
    return jsonify(results)


@scan_bp.route("/api/stats")
@login_required
def api_stats():
    """Return JSON with totals, daily breakdown, and top TLDs."""
    user_id = current_user.id if current_user.is_authenticated else None
    return jsonify(db.get_dashboard_stats(user_id=user_id))


@scan_bp.route("/api/history")
@login_required
def api_history():
    """Return the most recent scan records for the history table.

    Query param: limit (int, default 20, max 100).
    """
    limit = safe_int(request.args.get("limit"), default=20, min_val=1, max_val=100)
    user_id = current_user.id if current_user.is_authenticated else None
    return jsonify(db.get_recent_history(limit, user_id=user_id))


@scan_bp.route("/api/clear-history", methods=["POST"])
@login_required
def api_clear_history():
    """Clear all scan history for the authenticated user."""
    user_id = current_user.id
    deleted_count = db.clear_user_history(user_id)
    logger.info("User %d cleared %d scan records", user_id, deleted_count)
    return jsonify({"success": True, "deleted": deleted_count})
