"""User management in SQLite — register, login, lookup."""
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.engine import Engine

from backend.app.domain.schemas import new_id

AUTH_SCHEMA = [
    """CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        email TEXT NOT NULL UNIQUE,
        name TEXT NOT NULL,
        hashed_password TEXT NOT NULL,
        created_at TEXT NOT NULL
    )""",
]

# Migration: add user_id to sessions if not already there
AUTH_MIGRATIONS = [
    "ALTER TABLE sessions ADD COLUMN user_id TEXT REFERENCES users(id)",
]


class AuthError(Exception):
    """kind: email_taken | invalid_credentials | not_found"""
    def __init__(self, kind: str, message: str = ""):
        super().__init__(f"{kind}: {message}" if message else kind)
        self.kind = kind


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def setup_auth(engine: Engine) -> None:
    """Create auth tables and run safe migrations."""
    with engine.begin() as cx:
        for stmt in AUTH_SCHEMA:
            cx.execute(text(stmt))
        for stmt in AUTH_MIGRATIONS:
            try:
                cx.execute(text(stmt))
            except Exception:
                pass  # column already exists


class UserStore:
    def __init__(self, engine: Engine):
        self.engine = engine

    def create_user(self, email: str, name: str, hashed_password: str) -> dict:
        uid = new_id()
        try:
            with self.engine.begin() as cx:
                cx.execute(
                    text("INSERT INTO users VALUES (:id, :email, :name, :pw, :ts)"),
                    {"id": uid, "email": email.lower().strip(), "name": name.strip(), "pw": hashed_password, "ts": _now()},
                )
        except Exception as e:
            if "UNIQUE" in str(e).upper():
                raise AuthError("email_taken", "An account with that email already exists.")
            raise
        return self.get_by_id(uid)

    def get_by_email(self, email: str) -> dict | None:
        with self.engine.connect() as cx:
            row = cx.execute(
                text("SELECT * FROM users WHERE email = :e"),
                {"e": email.lower().strip()},
            ).mappings().first()
        return dict(row) if row else None

    def get_by_id(self, user_id: str) -> dict | None:
        with self.engine.connect() as cx:
            row = cx.execute(
                text("SELECT * FROM users WHERE id = :id"),
                {"id": user_id},
            ).mappings().first()
        return dict(row) if row else None

    def link_session(self, session_id: str, user_id: str) -> None:
        """Associate a session with a logged-in user (called after session creation when logged in)."""
        with self.engine.begin() as cx:
            cx.execute(
                text("UPDATE sessions SET user_id = :uid WHERE id = :sid"),
                {"uid": user_id, "sid": session_id},
            )

    def sessions_for_user(self, user_id: str) -> list[str]:
        """Return session IDs belonging to a user, newest first."""
        with self.engine.connect() as cx:
            rows = cx.execute(
                text("SELECT id FROM sessions WHERE user_id = :uid ORDER BY created_at DESC"),
                {"uid": user_id},
            ).fetchall()
        return [r[0] for r in rows]

    def user_stats(self, user_id: str) -> dict:
        """Aggregate stats for a user's dashboard."""
        with self.engine.connect() as cx:
            total_sessions = cx.execute(
                text("SELECT COUNT(*) FROM sessions WHERE user_id = :uid"), {"uid": user_id}
            ).scalar() or 0
            saved_orders = cx.execute(
                text("""SELECT COUNT(*) FROM work_orders wo
                        JOIN sessions s ON s.id = wo.session_id
                        WHERE s.user_id = :uid"""),
                {"uid": user_id},
            ).scalar() or 0
            languages = cx.execute(
                text("SELECT language, COUNT(*) as n FROM sessions WHERE user_id = :uid GROUP BY language"),
                {"uid": user_id},
            ).fetchall()
        return {
            "total_sessions": total_sessions,
            "saved_orders": saved_orders,
            "languages": {r[0]: r[1] for r in languages},
        }

