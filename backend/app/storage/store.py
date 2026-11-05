"""SQLite persistence. The no-unconfirmed-writes rule is enforced HERE, in the database.

A work order can only be inserted if (a) that exact revision was confirmed, (b) it is still the
session's current revision, and (c) the stored draft for it has zero open blockers. These are
SQLite triggers, so a bug in application code (or a direct SQL insert) cannot bypass them.
Transcript segments are immutable (update/delete are aborted by trigger). One work order per
session (UNIQUE) and one per idempotency key (UNIQUE).
"""
import json
from datetime import datetime, timezone

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import StaticPool

from backend.app.domain.schemas import Draft, SessionStatus, TranscriptSegment, WorkOrder, new_id

SCHEMA = [
    """CREATE TABLE IF NOT EXISTS sessions (
        id TEXT PRIMARY KEY, status TEXT NOT NULL, current_revision INTEGER NOT NULL,
        language TEXT NOT NULL, created_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS segments (
        id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id), turn_index INTEGER NOT NULL,
        body TEXT NOT NULL, UNIQUE (session_id, turn_index))""",
    """CREATE TABLE IF NOT EXISTS drafts (
        session_id TEXT NOT NULL REFERENCES sessions(id), revision INTEGER NOT NULL, body TEXT NOT NULL,
        open_blockers INTEGER NOT NULL, created_at TEXT NOT NULL, PRIMARY KEY (session_id, revision))""",
    """CREATE TABLE IF NOT EXISTS issue_attempts (
        session_id TEXT NOT NULL REFERENCES sessions(id), issue_key TEXT NOT NULL, n INTEGER NOT NULL,
        PRIMARY KEY (session_id, issue_key))""",
    """CREATE TABLE IF NOT EXISTS usage (
        scope TEXT NOT NULL, kind TEXT NOT NULL, n INTEGER NOT NULL, PRIMARY KEY (scope, kind))""",
    """CREATE TABLE IF NOT EXISTS confirmations (
        session_id TEXT NOT NULL REFERENCES sessions(id), revision INTEGER NOT NULL, actor TEXT NOT NULL,
        confirmed_at TEXT NOT NULL, PRIMARY KEY (session_id, revision))""",
    """CREATE TABLE IF NOT EXISTS work_orders (
        id TEXT PRIMARY KEY, session_id TEXT NOT NULL UNIQUE REFERENCES sessions(id),
        confirmed_revision INTEGER NOT NULL, idempotency_key TEXT NOT NULL UNIQUE,
        payload TEXT NOT NULL, evidence TEXT NOT NULL, created_at TEXT NOT NULL)""",
    """CREATE TRIGGER IF NOT EXISTS work_orders_guard BEFORE INSERT ON work_orders
       BEGIN
         SELECT RAISE(ABORT, 'not confirmed') WHERE NOT EXISTS (
           SELECT 1 FROM confirmations c WHERE c.session_id = NEW.session_id AND c.revision = NEW.confirmed_revision);
         SELECT RAISE(ABORT, 'stale revision') WHERE
           (SELECT current_revision FROM sessions WHERE id = NEW.session_id) IS NOT NEW.confirmed_revision;
         SELECT RAISE(ABORT, 'open blockers') WHERE
           (SELECT open_blockers FROM drafts WHERE session_id = NEW.session_id AND revision = NEW.confirmed_revision)
           IS NOT 0;
       END""",
    """CREATE TRIGGER IF NOT EXISTS confirmations_guard BEFORE INSERT ON confirmations
       BEGIN
         SELECT RAISE(ABORT, 'stale revision') WHERE
           (SELECT current_revision FROM sessions WHERE id = NEW.session_id) IS NOT NEW.revision;
         SELECT RAISE(ABORT, 'open blockers') WHERE
           (SELECT open_blockers FROM drafts WHERE session_id = NEW.session_id AND revision = NEW.revision) IS NOT 0;
       END""",
    "CREATE TRIGGER IF NOT EXISTS segments_no_update BEFORE UPDATE ON segments BEGIN SELECT RAISE(ABORT, 'segments are immutable'); END",
    "CREATE TRIGGER IF NOT EXISTS segments_no_delete BEFORE DELETE ON segments BEGIN SELECT RAISE(ABORT, 'segments are immutable'); END",
    "CREATE TRIGGER IF NOT EXISTS work_orders_no_update BEFORE UPDATE ON work_orders BEGIN SELECT RAISE(ABORT, 'saved work orders are not editable'); END",
    "CREATE TRIGGER IF NOT EXISTS work_orders_no_delete BEFORE DELETE ON work_orders BEGIN SELECT RAISE(ABORT, 'saved work orders are not editable'); END",
]


class StoreError(Exception):
    """kind: stale_revision | blockers_open | not_confirmed | idempotency_conflict | not_found"""

    def __init__(self, kind: str, message: str = ""):
        super().__init__(f"{kind}: {message}" if message else kind)
        self.kind = kind


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def make_engine(url: str = "sqlite://") -> Engine:
    kwargs = {"connect_args": {"check_same_thread": False}}
    if url in ("sqlite://", "sqlite:///:memory:"):
        kwargs["poolclass"] = StaticPool  # one shared connection: otherwise each thread would see its own empty database
    engine = create_engine(url, **kwargs)
    if url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def _fk(dbapi_conn, _):  # noqa: ANN001
            dbapi_conn.execute("PRAGMA foreign_keys = ON")
    return engine


class Store:
    def __init__(self, engine: Engine):
        self.engine = engine
        with engine.begin() as cx:
            for stmt in SCHEMA:
                cx.execute(text(stmt))

    # ---- sessions / segments / drafts

    def create_session(self, language: str = "mr") -> str:
        sid = new_id()
        draft = Draft(session_id=sid, revision=0)
        with self.engine.begin() as cx:
            cx.execute(text("INSERT INTO sessions VALUES (:id, :st, 0, :lang, :ts)"),
                       {"id": sid, "st": SessionStatus.DRAFT.value, "lang": language, "ts": _now()})
            cx.execute(text("INSERT INTO drafts VALUES (:id, 0, :body, 0, :ts)"),
                       {"id": sid, "body": draft.model_dump_json(), "ts": _now()})
        return sid

    def session(self, session_id: str) -> dict:
        with self.engine.connect() as cx:
            row = cx.execute(text("SELECT * FROM sessions WHERE id = :id"), {"id": session_id}).mappings().first()
        if row is None:
            raise StoreError("not_found", session_id)
        return dict(row)

    def set_language(self, session_id: str, language: str) -> None:
        with self.engine.begin() as cx:
            res = cx.execute(text("UPDATE sessions SET language = :l WHERE id = :id"), {"l": language, "id": session_id})
            if res.rowcount != 1:
                raise StoreError("not_found", session_id)

    def add_segment(self, seg_kwargs: dict) -> TranscriptSegment:
        """seg_kwargs: session_id, text, source, plus optional language_code/model/request_id/audio_ref."""
        with self.engine.begin() as cx:
            n = cx.execute(text("SELECT COUNT(*) FROM segments WHERE session_id = :s"),
                           {"s": seg_kwargs["session_id"]}).scalar()
            seg = TranscriptSegment(turn_index=n, **seg_kwargs)
            cx.execute(text("INSERT INTO segments VALUES (:id, :s, :n, :body)"),
                       {"id": seg.id, "s": seg.session_id, "n": n, "body": seg.model_dump_json()})
        return seg

    def segments(self, session_id: str) -> dict[str, TranscriptSegment]:
        with self.engine.connect() as cx:
            rows = cx.execute(text("SELECT body FROM segments WHERE session_id = :s ORDER BY turn_index"),
                              {"s": session_id}).scalars().all()
        return {s.id: s for s in (TranscriptSegment.model_validate_json(r) for r in rows)}

    def draft(self, session_id: str, revision: int | None = None) -> Draft:
        rev = self.session(session_id)["current_revision"] if revision is None else revision
        with self.engine.connect() as cx:
            body = cx.execute(text("SELECT body FROM drafts WHERE session_id = :s AND revision = :r"),
                              {"s": session_id, "r": rev}).scalar()
        if body is None:
            raise StoreError("not_found", f"draft {session_id}@{rev}")
        return Draft.model_validate_json(body)

    def save_draft(self, draft: Draft) -> None:
        """Compare-and-set: only current_revision + 1 may be stored."""
        with self.engine.begin() as cx:
            res = cx.execute(text("UPDATE sessions SET current_revision = :new, status = :st "
                                  "WHERE id = :id AND current_revision = :old AND status != 'saved'"),
                             {"new": draft.revision, "old": draft.revision - 1, "id": draft.session_id,
                              "st": (SessionStatus.NEEDS_CLARIFICATION if draft.open_blockers()
                                     else SessionStatus.READY_FOR_REVIEW).value})
            if res.rowcount != 1:
                raise StoreError("stale_revision", f"cannot store revision {draft.revision}")
            cx.execute(text("INSERT INTO drafts VALUES (:id, :rev, :body, :nb, :ts)"),
                       {"id": draft.session_id, "rev": draft.revision, "body": draft.model_dump_json(),
                        "nb": len(draft.open_blockers()), "ts": _now()})

    # ---- confirm + commit

    def confirm(self, session_id: str, revision: int, actor: str = "user") -> None:
        draft_row = self.draft(session_id, revision)
        if draft_row.open_blockers():
            raise StoreError("blockers_open", f"{len(draft_row.open_blockers())} blocking issue(s)")
        try:
            with self.engine.begin() as cx:
                cx.execute(text("INSERT OR IGNORE INTO confirmations VALUES (:s, :r, :a, :ts)"),
                           {"s": session_id, "r": revision, "a": actor, "ts": _now()})
                cx.execute(text("UPDATE sessions SET status = 'awaiting_confirmation' WHERE id = :s AND status != 'saved'"),
                           {"s": session_id})
        except IntegrityError as e:
            raise _from_db(e) from e

    def commit(self, session_id: str, revision: int, idempotency_key: str, payload: dict,
               evidence: list[dict]) -> WorkOrder:
        """Insert the work order. Retrying the same key for the same session+revision returns the same record."""
        with self.engine.connect() as cx:
            prior = cx.execute(text("SELECT * FROM work_orders WHERE idempotency_key = :k"),
                               {"k": idempotency_key}).mappings().first()
        if prior is not None:
            if prior["session_id"] == session_id and prior["confirmed_revision"] == revision:
                return _wo(prior)
            raise StoreError("idempotency_conflict", "key already used for a different request")
        wo = WorkOrder(session_id=session_id, confirmed_revision=revision, payload=payload,
                       evidence_snapshot=[])  # evidence stored as JSON below
        try:
            with self.engine.begin() as cx:
                cx.execute(text("INSERT INTO work_orders VALUES (:id, :s, :r, :k, :p, :e, :ts)"),
                           {"id": wo.id, "s": session_id, "r": revision, "k": idempotency_key,
                            "p": json.dumps(payload, ensure_ascii=False), "e": json.dumps(evidence, ensure_ascii=False),
                            "ts": _now()})
                cx.execute(text("UPDATE sessions SET status = 'saved' WHERE id = :s"), {"s": session_id})
        except IntegrityError as e:
            raise _from_db(e) from e
        return wo

    def bump_attempts(self, session_id: str, issue_key: str) -> int:
        """Count one answer that could not be understood for this question. Not part of the draft."""
        with self.engine.begin() as cx:
            cx.execute(text("INSERT INTO issue_attempts VALUES (:s, :k, 1) "
                            "ON CONFLICT(session_id, issue_key) DO UPDATE SET n = n + 1"),
                       {"s": session_id, "k": issue_key})
            return cx.execute(text("SELECT n FROM issue_attempts WHERE session_id = :s AND issue_key = :k"),
                              {"s": session_id, "k": issue_key}).scalar()

    def take(self, scope: str, kind: str, limit: int) -> bool:
        """Atomically use one unit of a quota (e.g. scope "day:2026-11-04", kind "stt"). False when exhausted."""
        with self.engine.begin() as cx:
            cx.execute(text("INSERT INTO usage VALUES (:s, :k, 0) ON CONFLICT(scope, kind) DO NOTHING"),
                       {"s": scope, "k": kind})
            res = cx.execute(text("UPDATE usage SET n = n + 1 WHERE scope = :s AND kind = :k AND n < :lim"),
                             {"s": scope, "k": kind, "lim": limit})
            return res.rowcount == 1

    def used(self, scope: str, kind: str) -> int:
        with self.engine.connect() as cx:
            return cx.execute(text("SELECT n FROM usage WHERE scope = :s AND kind = :k"), {"s": scope, "k": kind}).scalar() or 0

    def attempts(self, session_id: str, issue_key: str) -> int:
        with self.engine.connect() as cx:
            return cx.execute(text("SELECT n FROM issue_attempts WHERE session_id = :s AND issue_key = :k"),
                              {"s": session_id, "k": issue_key}).scalar() or 0

    def work_order_for(self, session_id: str) -> dict | None:
        with self.engine.connect() as cx:
            row = cx.execute(text("SELECT * FROM work_orders WHERE session_id = :s"), {"s": session_id}).mappings().first()
        return dict(row) if row else None


def _wo(row) -> WorkOrder:
    return WorkOrder(id=row["id"], session_id=row["session_id"], confirmed_revision=row["confirmed_revision"],
                     payload=json.loads(row["payload"]))


def _from_db(e: IntegrityError) -> StoreError:
    msg = str(e.orig)
    for needle, kind in (("not confirmed", "not_confirmed"), ("stale revision", "stale_revision"),
                         ("open blockers", "blockers_open"), ("work_orders.session_id", "already_saved"),
                         ("idempotency_key", "idempotency_conflict")):
        if needle in msg:
            return StoreError(kind, msg)
    return StoreError("db_error", msg)
