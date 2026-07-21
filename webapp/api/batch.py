"""api/batch.py — Blueprint for the batch CSV scanner endpoint."""

import csv
import io
import json
import logging

from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required

import models.loader as loader
import database.db as db
from api.helpers import safe_int, MAX_URL_LENGTH

logger = logging.getLogger(__name__)
batch_bp = Blueprint("batch", __name__)

BATCH_MAX_URLS = 1000


@batch_bp.route("/api/batch", methods=["POST"])
@login_required
def api_batch():
    """Accept a CSV file upload and scan all URLs using classical models only.

    Form field: "file" — CSV with a column named url/URL/link/urls.
    Form field: "max_urls" (optional int, default 1000, cap 1000).
    Returns JSON with per-URL results and summary statistics.
    """
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    f = request.files["file"]
    if not f.filename or not f.filename.lower().endswith(".csv"):
        return jsonify({"error": "File must be a .csv"}), 400

    max_urls = safe_int(
        request.form.get("max_urls"), default=1000, min_val=1, max_val=BATCH_MAX_URLS
    )

    try:
        content = f.read().decode("utf-8", errors="replace")
        reader = csv.DictReader(io.StringIO(content))
    except Exception as exc:
        return jsonify({"error": f"Could not parse CSV: {exc}"}), 400

    # Case-insensitive column name matching so "Url", "URL", "url" all work.
    fieldnames_lower = {name.lower(): name for name in (reader.fieldnames or [])}
    url_col = None
    for candidate in ("url", "urls", "link", "links", "address"):
        if candidate in fieldnames_lower:
            url_col = fieldnames_lower[candidate]
            break
    if url_col is None:
        return jsonify({
            "error": "CSV must have a column named 'url', 'link', or 'address'",
            "columns_found": reader.fieldnames,
        }), 400

    rows = [r for r in reader if (r.get(url_col) or "").strip()][:max_urls]
    if not rows:
        return jsonify({"error": "No URLs found in file"}), 400

    results_list = []
    db_rows = []
    model_counts = {"knn": 0, "logreg": 0, "nb": 0, "svm": 0, "rf": 0, "mlp": 0}
    tld_counts: dict[str, int] = {}
    classical_model_keys = list(model_counts.keys())

    for row in rows:
        url = row[url_col].strip()

        # Skip URLs that are too long rather than crashing.
        if len(url) > MAX_URL_LENGTH:
            results_list.append({
                "url":            url[:120] + "…",
                "verdict":        "error",
                "confidence":     0.0,
                "phishing_votes": 0,
                "total_models":   0,
            })
            continue

        try:
            pred = loader.predict_all(url, include_quantum=False)
        except Exception:
            logger.exception("predict_all failed for url %r — skipping", url[:80])
            results_list.append({
                "url":            url,
                "verdict":        "error",
                "confidence":     0.0,
                "phishing_votes": 0,
                "total_models":   0,
            })
            continue

        verdict    = pred["ensemble"]["verdict"]
        confidence = pred["ensemble"]["confidence"]  # consistent with single-scan endpoint
        phishing_votes = pred["ensemble"]["phishing_votes"]

        for m in classical_model_keys:
            if pred.get(m) and pred[m]["verdict"] == "bad":
                model_counts[m] += 1

        # TLD aggregation reuses the same logic as the DB layer.
        tld = db._extract_tld(url)
        if tld:
            tld_counts[tld] = tld_counts.get(tld, 0) + 1

        # Collect per-model predictions (classical only)
        model_details = {}
        for model_key in classical_model_keys:
            if pred.get(model_key):
                model_details[model_key] = {
                    "verdict": pred[model_key]["verdict"],
                    "confidence": pred[model_key]["confidence"],
                }

        results_list.append({
            "url":            url,
            "verdict":        verdict,
            "confidence":     confidence,
            "phishing_votes": phishing_votes,
            "total_models":   pred["ensemble"]["total_models"],
            "models":         model_details,
        })

        model_snapshot = {
            m: pred[m] for m in classical_model_keys if pred.get(m) is not None
        }
        db_rows.append((url, verdict, confidence, json.dumps(model_snapshot)))

    user_id = current_user.id if current_user.is_authenticated else None
    try:
        db.save_scans_batch(db_rows, user_id=user_id)
    except Exception:
        # A DB write failure must not discard scan results already computed.
        logger.exception("Failed to persist batch of %d scans", len(db_rows))

    phishing_count = sum(1 for r in results_list if r["verdict"] == "bad")
    total = len(results_list)
    top_tlds = sorted(tld_counts, key=tld_counts.get, reverse=True)[:5]

    return jsonify({
        "total":        total,
        "phishing":     phishing_count,
        "safe":         total - phishing_count,
        "phishing_pct": round(phishing_count / total * 100, 1) if total else 0,
        "model_counts": model_counts,
        "top_tlds":     [{"tld": t, "count": tld_counts[t]} for t in top_tlds],
        "results":      results_list,
    })
