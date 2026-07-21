"""database/users.py — User and session management for PhishGuard auth."""
from __future__ import annotations

import logging
import sqlite3
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

from database.db import _get_conn

logger = logging.getLogger(__name__)


def init_user_tables() -> None:
    """Create auth tables and migrate existing scans table with user_id column."""
    con = _get_conn()
    try:
        # Check if we need to migrate from old OAuth schema
        cursor = con.execute("PRAGMA table_info(users)")
        columns = {row[1] for row in cursor.fetchall()}

        if "google_id" in columns:
            # Old schema exists, migrate it
            logger.info("Migrating from old OAuth schema to simple password auth")
            con.execute("""
                CREATE TABLE IF NOT EXISTS users_new (
                    id          INTEGER  PRIMARY KEY AUTOINCREMENT,
                    email       TEXT     UNIQUE NOT NULL,
                    password    TEXT     NOT NULL,
                    name        TEXT     NOT NULL,
                    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
                    last_login  DATETIME DEFAULT CURRENT_TIMESTAMP,
                    is_active   INTEGER  DEFAULT 1
                )
            """)
            # Migrate data from old table (only if password column exists)
            try:
                con.execute("""
                    INSERT INTO users_new (id, email, password, name, created_at, last_login, is_active)
                    SELECT id, email, COALESCE(password, ''), COALESCE(name, email), created_at, last_login, is_active
                    FROM users
                """)
            except sqlite3.OperationalError:
                # password column doesn't exist, skip data migration
                logger.info("No existing user data to migrate")

            con.execute("DROP TABLE users")
            con.execute("ALTER TABLE users_new RENAME TO users")
            logger.info("Completed migration from OAuth to password auth")
        else:
            # New schema, just create it
            con.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id          INTEGER  PRIMARY KEY AUTOINCREMENT,
                    email       TEXT     UNIQUE NOT NULL,
                    password    TEXT     NOT NULL,
                    name        TEXT     NOT NULL,
                    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
                    last_login  DATETIME DEFAULT CURRENT_TIMESTAMP,
                    is_active   INTEGER  DEFAULT 1
                )
            """)

        con.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)")

        # Migrate scans table: add user_id FK if missing (safe on repeated startup)
        try:
            con.execute("ALTER TABLE scans ADD COLUMN user_id INTEGER REFERENCES users(id)")
            con.execute("CREATE INDEX IF NOT EXISTS idx_scans_user_id ON scans(user_id)")
            logger.info("Migrated scans table: added user_id column")
        except sqlite3.OperationalError:
            pass  # Column already exists — normal on repeated startups

        con.commit()
        logger.info("Auth tables ready")
    finally:
        con.close()


def create_user(email: str, password: str, name: str) -> dict:
    """Create a new user with hashed password. Returns user dict."""
    now = datetime.utcnow().isoformat(sep=" ", timespec="seconds")
    password_hash = generate_password_hash(password)
    con = _get_conn()
    try:
        con.execute(
            """
            INSERT INTO users (email, password, name, created_at, last_login)
            VALUES (?, ?, ?, ?, ?)
            """,
            (email, password_hash, name, now, now),
        )
        con.commit()
        return get_user_by_email(email)  # type: ignore[return-value]
    finally:
        con.close()


def get_user_by_id(user_id: int) -> dict | None:
    con = _get_conn()
    try:
        con.row_factory = sqlite3.Row
        row = con.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return dict(row) if row else None
    finally:
        con.close()


def get_user_by_email(email: str) -> dict | None:
    con = _get_conn()
    try:
        con.row_factory = sqlite3.Row
        row = con.execute(
            "SELECT * FROM users WHERE email = ?", (email,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        con.close()


def verify_password(stored_hash: str, password: str) -> bool:
    """Verify a password against its hash."""
    return check_password_hash(stored_hash, password)


def get_user_scans(user_id: int, limit: int = 50) -> list[dict]:
    """Return scans attributed to this user, newest first."""
    con = _get_conn()
    try:
        rows = con.execute(
            "SELECT id, url, verdict, confidence, timestamp FROM scans "
            "WHERE user_id = ? ORDER BY timestamp DESC LIMIT ?",
            (user_id, limit),
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


def get_user_scan_count(user_id: int) -> int:
    con = _get_conn()
    try:
        return con.execute(
            "SELECT COUNT(*) FROM scans WHERE user_id = ?", (user_id,)
        ).fetchone()[0]
    finally:
        con.close()


def delete_user(user_id: int) -> None:
    """Soft-delete: mark user and their sessions as inactive."""
    con = _get_conn()
    try:
        con.execute("UPDATE users         SET is_active = 0 WHERE id      = ?", (user_id,))
        con.execute("UPDATE login_sessions SET is_active = 0 WHERE user_id = ?", (user_id,))
        con.commit()
        logger.info("Soft-deleted user id=%s", user_id)
    finally:
        con.close()


def get_user_scan_stats(user_id: int) -> dict:
    """Return detailed scan statistics for a user."""
    con = _get_conn()
    try:
        total = con.execute(
            "SELECT COUNT(*) FROM scans WHERE user_id = ?", (user_id,)
        ).fetchone()[0]

        phishing = con.execute(
            "SELECT COUNT(*) FROM scans WHERE user_id = ? AND verdict = 'bad'", (user_id,)
        ).fetchone()[0]

        safe = total - phishing
        phishing_pct = round((phishing / total * 100), 1) if total else 0

        recent_30d = con.execute(
            "SELECT COUNT(*) FROM scans WHERE user_id = ? AND timestamp >= datetime('now', '-30 days')",
            (user_id,)
        ).fetchone()[0]

        return {
            "total_scans": total,
            "phishing_count": phishing,
            "safe_count": safe,
            "phishing_percentage": phishing_pct,
            "scans_last_30_days": recent_30d,
        }
    finally:
        con.close()


def verify_user_scan_connection(user_id: int) -> bool:
    """Verify that a user has been properly linked to their scans in the database."""
    con = _get_conn()
    try:
        # Check if user exists
        user_exists = con.execute(
            "SELECT COUNT(*) FROM users WHERE id = ?", (user_id,)
        ).fetchone()[0]

        if not user_exists:
            return False

        # Check if user has any associated scans
        has_scans = con.execute(
            "SELECT COUNT(*) FROM scans WHERE user_id = ?", (user_id,)
        ).fetchone()[0]

        return has_scans > 0
    finally:
        con.close()
