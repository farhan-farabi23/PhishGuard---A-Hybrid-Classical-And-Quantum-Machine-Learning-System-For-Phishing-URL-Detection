"""auth/models.py — Flask-Login User model backed by raw SQLite."""
from __future__ import annotations

from flask_login import UserMixin

import database.users as users_db


class User(UserMixin):
    """Thin wrapper around a users row that satisfies Flask-Login's interface."""

    def __init__(self, row: dict) -> None:
        self.id: int = row["id"]
        self.email: str = row["email"]
        self.name: str = row["name"]
        self.created_at: str = row.get("created_at", "")
        self.last_login: str = row.get("last_login", "")
        self._is_active: bool = bool(row.get("is_active", 1))

    # Flask-Login interface -------------------------------------------------

    @property
    def is_active(self) -> bool:  # type: ignore[override]
        return self._is_active

    def get_id(self) -> str:
        return str(self.id)

    # Factory methods -------------------------------------------------------

    @staticmethod
    def get(user_id: int) -> "User | None":
        row = users_db.get_user_by_id(user_id)
        return User(row) if row else None

    @staticmethod
    def get_by_email(email: str) -> "User | None":
        row = users_db.get_user_by_email(email)
        return User(row) if row else None
