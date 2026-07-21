"""db.py — SQLite scan history for PhishGuard."""

import json
import logging
import os
import sqlite3

logger = logging.getLogger(__name__)

# Allow overriding the DB path via environment variable for testing / deployment.
_default_db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "phishguard.db")
DB_PATH: str = os.environ.get("PHISHGUARD_DB_PATH", _default_db_path)


def _get_conn() -> sqlite3.Connection:
    """Open a WAL-mode connection to the database."""
    con = sqlite3.connect(DB_PATH, check_same_thread=False)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")
    return con


def _extract_tld(url: str) -> str:
    """Extract the TLD (e.g. '.com') from a URL, or '' if unparseable."""
    try:
        host = url.split("//")[-1].split("/")[0]
        parts = host.split(".")
        return ("." + parts[-1].lower()) if len(parts) >= 2 else ""
    except Exception:
        return ""


def init_db() -> None:
    """Create the scans table and indexes if they do not exist."""
    con = _get_conn()
    try:
        con.execute("""
            CREATE TABLE IF NOT EXISTS scans (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                url        TEXT    NOT NULL,
                verdict    TEXT    NOT NULL,
                confidence REAL,
                tld        TEXT    DEFAULT '',
                timestamp  DATETIME DEFAULT CURRENT_TIMESTAMP,
                results    TEXT,
                user_id    INTEGER REFERENCES users(id)
            )
        """)
        # Migration: add tld column to databases created before this column existed.
        try:
            con.execute("ALTER TABLE scans ADD COLUMN tld TEXT DEFAULT ''")
        except sqlite3.OperationalError:
            pass  # Column already exists — normal on repeated startups
        # Migration: add user_id column (safe on repeated startup)
        try:
            con.execute("ALTER TABLE scans ADD COLUMN user_id INTEGER REFERENCES users(id)")
        except sqlite3.OperationalError:
            pass  # Column already exists — normal on repeated startups
        con.execute("CREATE INDEX IF NOT EXISTS idx_scans_timestamp ON scans(timestamp)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_scans_tld ON scans(tld)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_scans_user_id ON scans(user_id)")
        con.commit()
    finally:
        con.close()


def save_scan(
    url: str,
    verdict: str,
    confidence: float,
    results: dict,
    user_id: "int | None" = None,
) -> None:
    """Insert one scan record into the database."""
    con = _get_conn()
    try:
        con.execute(
            "INSERT INTO scans (url, verdict, confidence, tld, results, user_id)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (url, verdict, confidence, _extract_tld(url), json.dumps(results), user_id),
        )
        con.commit()
    finally:
        con.close()


def save_scans_batch(scans: list[tuple], user_id: "int | None" = None) -> None:
    """Insert multiple scan records in a single transaction.

    Args:
        scans: List of (url, verdict, confidence, results_json_str) tuples.
        user_id: Optional user ID to associate all scans with an authenticated user.
    """
    con = _get_conn()
    try:
        con.executemany(
            "INSERT INTO scans (url, verdict, confidence, tld, results, user_id) VALUES (?, ?, ?, ?, ?, ?)",
            [
                (url, verdict, confidence, _extract_tld(url), results_json, user_id)
                for url, verdict, confidence, results_json in scans
            ],
        )
        con.commit()
    finally:
        con.close()


def get_dashboard_stats(user_id: "int | None" = None) -> dict:
    """Return all stats needed by the analytics dashboard, filtered by user if provided."""
    con = _get_conn()
    try:
        user_filter = "WHERE user_id = ?" if user_id else ""
        user_param = (user_id,) if user_id else ()

        total    = con.execute(f"SELECT COUNT(*) FROM scans {user_filter}", user_param).fetchone()[0]
        phishing = con.execute(f"SELECT COUNT(*) FROM scans {user_filter} AND verdict = 'bad'" if user_filter else "SELECT COUNT(*) FROM scans WHERE verdict = 'bad'", user_param).fetchone()[0]
        today    = con.execute(
            f"SELECT COUNT(*) FROM scans {user_filter} AND date(timestamp) = date('now')" if user_filter else "SELECT COUNT(*) FROM scans WHERE date(timestamp) = date('now')",
            user_param
        ).fetchone()[0]
        this_week = con.execute(
            f"SELECT COUNT(*) FROM scans {user_filter} AND timestamp >= datetime('now', '-7 days')" if user_filter else "SELECT COUNT(*) FROM scans WHERE timestamp >= datetime('now', '-7 days')",
            user_param
        ).fetchone()[0]

        daily_rows = con.execute(f"""
            SELECT date(timestamp)                                   AS day,
                   COUNT(*)                                          AS total,
                   SUM(CASE WHEN verdict = 'bad' THEN 1 ELSE 0 END) AS phishing
            FROM   scans
            {user_filter} {'AND' if user_filter else 'WHERE'} timestamp >= datetime('now', '-7 days')
            GROUP  BY day
            ORDER  BY day
        """, user_param).fetchall()

        # TLD aggregation via SQL — avoids loading all URLs into Python memory.
        tld_rows = con.execute(f"""
            SELECT tld, COUNT(*) AS cnt
            FROM   scans
            {user_filter} {'AND' if user_filter else 'WHERE'} tld != ''
            GROUP  BY tld
            ORDER  BY cnt DESC
            LIMIT  8
        """, user_param).fetchall()
    finally:
        con.close()

    return {
        "total":        total,
        "phishing":     phishing,
        "safe":         total - phishing,
        "phishing_pct": round(phishing / total * 100, 1) if total else 0,
        "today":        today,
        "this_week":    this_week,
        "daily_counts": [
            {"date": r[0], "total": r[1], "phishing": r[2]}
            for r in daily_rows
        ],
        "top_tlds": [
            {"tld": r[0], "count": r[1]} for r in tld_rows
        ],
    }


def get_recent_history(limit: int = 20, user_id: "int | None" = None) -> list[dict]:
    """Return a list of dicts for the history table, filtered by user if provided."""
    con = _get_conn()
    try:
        if user_id:
            rows = con.execute(
                "SELECT id, url, verdict, confidence, timestamp FROM scans "
                "WHERE user_id = ? "
                "ORDER BY timestamp DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT id, url, verdict, confidence, timestamp FROM scans "
                "ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            ).fetchall()
    finally:
        con.close()
    return [
        {
            "id":         r[0],
            "url":        r[1],
            "verdict":    r[2],
            "confidence": r[3],
            "timestamp":  r[4],
        }
        for r in rows
    ]


def clear_user_history(user_id: int) -> int:
    """Delete all scan records for a specific user. Returns number of rows deleted."""
    con = _get_conn()
    try:
        cursor = con.execute("DELETE FROM scans WHERE user_id = ?", (user_id,))
        con.commit()
        return cursor.rowcount
    finally:
        con.close()
