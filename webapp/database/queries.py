"""Database queries for PhishGuard — User profiles, scan history, analytics."""

from datetime import datetime
from database.db import _get_conn


def get_user_by_id(user_id):
    """Get user profile information with computed fields (initials, member_since)."""
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT id, name, email, created_at FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        return None

    name = row["name"]
    initials = "".join(w[0].upper() for w in name.split() if w)
    member_since = datetime.strptime(row["created_at"], "%Y-%m-%d %H:%M:%S").strftime(
        "%B %Y"
    )

    return {
        "id": row["id"],
        "name": name,
        "email": row["email"],
        "initials": initials,
        "member_since": member_since,
    }


def get_user_scan_stats(user_id, date_from=None, date_to=None):
    """Get scan statistics for a user (total scans, phishing detected, safe URLs)."""
    date_clause, date_params = _build_date_filter(date_from, date_to)
    params = [user_id] + date_params

    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT COALESCE(COUNT(*), 0) AS total, "
            "       COALESCE(SUM(CASE WHEN verdict = 'bad' THEN 1 ELSE 0 END), 0) AS phishing "
            "FROM scans WHERE user_id = ? " + date_clause,
            params,
        ).fetchone()
    finally:
        conn.close()

    total = row["total"] if row else 0
    phishing = row["phishing"] if row else 0
    safe = total - phishing

    return {
        "total": total,
        "phishing": phishing,
        "safe": safe,
        "phishing_pct": round(phishing / total * 100, 1) if total > 0 else 0,
    }


def _build_date_filter(date_from, date_to):
    """Build SQL date filter clause and parameters."""
    if date_from and date_to:
        return "AND date(timestamp) BETWEEN ? AND ?", [date_from, date_to]
    return "", []


def get_user_recent_scans(user_id, limit=15, date_from=None, date_to=None):
    """Get recent scan history for a user."""
    date_clause, date_params = _build_date_filter(date_from, date_to)
    params = [user_id] + date_params + [limit]

    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT id, url, verdict, confidence, timestamp "
            "FROM scans "
            "WHERE user_id = ? " + date_clause + " ORDER BY timestamp DESC LIMIT ?",
            params,
        ).fetchall()
    finally:
        conn.close()

    return [
        {
            "id": row["id"],
            "url": row["url"][:60] + "..." if len(row["url"]) > 60 else row["url"],
            "url_full": row["url"],
            "verdict": row["verdict"],
            "verdict_display": "🚫 Phishing" if row["verdict"] == "bad" else "✓ Safe",
            "confidence": f"{row['confidence']:.1%}",
            "timestamp": datetime.strptime(row["timestamp"], "%Y-%m-%d %H:%M:%S").strftime("%d %b %Y, %H:%M"),
        }
        for row in rows
    ]


def get_user_verdict_summary(user_id, date_from=None, date_to=None):
    """Get verdict breakdown by category for a user."""
    date_clause, date_params = _build_date_filter(date_from, date_to)
    params = [user_id] + date_params

    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT verdict, COUNT(*) AS count FROM scans "
            "WHERE user_id = ? " + date_clause + " GROUP BY verdict ORDER BY count DESC",
            params,
        ).fetchall()
    finally:
        conn.close()

    total = sum(r["count"] for r in rows)
    if total == 0:
        return []

    result = []
    for r in rows:
        label = "Phishing Detected" if r["verdict"] == "bad" else "Safe URLs"
        pct = int(r["count"] / total * 100)
        result.append({
            "label": label,
            "count": r["count"],
            "percent": pct,
            "class": "phishing" if r["verdict"] == "bad" else "safe",
        })

    # Ensure percentages add up to 100
    if result:
        result[0]["percent"] += 100 - sum(r["percent"] for r in result)

    return result


def get_scan_detail(scan_id, user_id):
    """Get full details of a single scan (for detail view)."""
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT id, url, verdict, confidence, results, timestamp FROM scans "
            "WHERE id = ? AND user_id = ?",
            (scan_id, user_id),
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        return None

    import json
    results = json.loads(row["results"]) if row["results"] else {}

    return {
        "id": row["id"],
        "url": row["url"],
        "verdict": row["verdict"],
        "verdict_display": "🚫 Phishing Detected" if row["verdict"] == "bad" else "✓ Safe",
        "confidence": f"{row['confidence']:.1%}",
        "timestamp": datetime.strptime(row["timestamp"], "%Y-%m-%d %H:%M:%S").strftime("%d %b %Y, %H:%M:%S"),
        "model_votes": results.get("model_votes", {}),
    }
