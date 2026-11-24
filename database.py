import getpass
import hashlib
import logging
import os
import sqlite3
import time
from argparse import ArgumentParser
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import (
    Boolean,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    create_engine,
    event,
    func,
    or_,
    update,
)
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    joinedload,
    mapped_column,
    noload,
    relationship,
)

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1


@dataclass(frozen=True)
class EntrySummary:
    id: int
    text: str
    visit_count: int
    example: str | None = None


@dataclass(frozen=True)
class UserRecord:
    id: int
    username: str
    is_admin: bool
    is_active: bool
    session_version: int
    last_review_question_id: int | None
    created_at: int


@dataclass(frozen=True)
class UserAdminSummary:
    id: int
    username: str
    is_admin: bool
    is_active: bool
    created_at: int
    entry_count: int


@dataclass(frozen=True)
class ApiTokenRecord:
    id: int
    user_id: int
    label: str
    created_at: int
    last_used_at: int | None


@dataclass(frozen=True)
class InviteTokenRecord:
    id: int
    note: str
    created_at: int
    expires_at: int
    used_at: int | None
    used_by_username: str | None = None


@dataclass(frozen=True)
class CaptureItemRecord:
    id: int
    page_note_id: int
    word: str
    context: str
    definition_text: str
    timestamp_seconds: int | None
    promoted_entry_id: int | None
    created_at: int


@dataclass(frozen=True)
class PageNoteRecord:
    id: int
    url: str
    title: str
    notes_md: str
    created_at: int
    updated_at: int
    items: list[CaptureItemRecord]


def hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(
    os.environ.get("DICTIONARY_DB_PATH", str(BASE_DIR / "dictionary.db"))
).resolve()

engine = create_engine(
    f"sqlite:///{DB_PATH}",
    # echo=True,
    future=True,
    pool_recycle=3600,
    pool_pre_ping=True,
)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "user"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(
        String(collation="NOCASE"), nullable=False, unique=True
    )
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    session_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # Intentionally a plain nullable integer (no FK back to question.id) to avoid
    # a circular foreign-key cycle with question.user_id on SQLite.
    last_review_question_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[int] = mapped_column(Integer, nullable=False)


class ApiToken(Base):
    __tablename__ = "api_token"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True
    )
    label: Mapped[str] = mapped_column(String, nullable=False, default="Chrome Extension")
    token_hash: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
    created_at: Mapped[int] = mapped_column(Integer, nullable=False)
    last_used_at: Mapped[int | None] = mapped_column(Integer, nullable=True)


class InviteToken(Base):
    __tablename__ = "invite_token"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token_hash: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
    note: Mapped[str] = mapped_column(String, nullable=False, default="")
    created_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    used_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[int] = mapped_column(Integer, nullable=False)
    expires_at: Mapped[int] = mapped_column(Integer, nullable=False)
    used_at: Mapped[int | None] = mapped_column(Integer, nullable=True)


class PasswordResetToken(Base):
    __tablename__ = "password_reset_token"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
    created_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[int] = mapped_column(Integer, nullable=False)
    expires_at: Mapped[int] = mapped_column(Integer, nullable=False)
    used_at: Mapped[int | None] = mapped_column(Integer, nullable=True)


class Entry(Base):
    # NOTE: DB table is still named "question" to stay compatible with existing data.
    __tablename__ = "question"
    __table_args__ = (
        UniqueConstraint("user_id", "text", name="uq_question_user_text"),
        Index("ix_question_user_id_id", "user_id", "id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
    text: Mapped[str] = mapped_column(String, nullable=False)
    definitions: Mapped[list["Definition"]] = relationship(
        "Definition",
        back_populates="entry",
        lazy="joined",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    example: Mapped[str | None] = mapped_column(String, nullable=True)
    is_hidden: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    visit_count: Mapped[int] = mapped_column(Integer, nullable=True, default=0)
    last_visit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_review: Mapped[int | None] = mapped_column(Integer, nullable=True)

    def __str__(self) -> str:
        return (
            f'Entry(id={self.id}, user_id={self.user_id}, text="{self.text}",'
            f" definitions={[str(d) for d in self.definitions]})"
            f" example: {self.example}"
        )


class Definition(Base):
    # NOTE: DB table is still named "answer" to stay compatible with existing data.
    __tablename__ = "answer"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    text: Mapped[str] = mapped_column(String, nullable=False)
    question_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("question.id", ondelete="CASCADE")
    )
    entry: Mapped[Entry] = relationship(Entry, back_populates="definitions")

    def __str__(self) -> str:
        return f'Definition(id={self.id}, text="{self.text}")'


class PageNote(Base):
    __tablename__ = "page_note"
    __table_args__ = (
        UniqueConstraint("user_id", "url", name="uq_page_note_user_url"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
    url: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False, default="")
    notes_md: Mapped[str] = mapped_column(String, nullable=False, default="")
    created_at: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_at: Mapped[int] = mapped_column(Integer, nullable=False)
    items: Mapped[list["PageCaptureItem"]] = relationship(
        "PageCaptureItem",
        back_populates="page_note",
        order_by="PageCaptureItem.id.asc()",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class PageCaptureItem(Base):
    __tablename__ = "page_capture_item"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    page_note_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("page_note.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    word: Mapped[str] = mapped_column(String, nullable=False)
    context: Mapped[str] = mapped_column(String, nullable=False, default="")
    definition_text: Mapped[str] = mapped_column(String, nullable=False, default="")
    timestamp_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    promoted_entry_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("question.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[int] = mapped_column(Integer, nullable=False)
    page_note: Mapped[PageNote] = relationship(PageNote, back_populates="items")


def _to_user_record(user: User) -> UserRecord:
    return UserRecord(
        id=user.id,
        username=user.username,
        is_admin=bool(user.is_admin),
        is_active=bool(user.is_active),
        session_version=user.session_version,
        last_review_question_id=user.last_review_question_id,
        created_at=user.created_at,
    )


def _to_api_token_record(token: ApiToken) -> ApiTokenRecord:
    return ApiTokenRecord(
        id=token.id,
        user_id=token.user_id,
        label=token.label,
        created_at=token.created_at,
        last_used_at=token.last_used_at,
    )


def _to_item_record(item: PageCaptureItem) -> CaptureItemRecord:
    return CaptureItemRecord(
        id=item.id,
        page_note_id=item.page_note_id,
        word=item.word,
        context=item.context,
        definition_text=item.definition_text,
        timestamp_seconds=item.timestamp_seconds,
        promoted_entry_id=item.promoted_entry_id,
        created_at=item.created_at,
    )


def _to_page_note_record(note: PageNote) -> PageNoteRecord:
    return PageNoteRecord(
        id=note.id,
        url=note.url,
        title=note.title,
        notes_md=note.notes_md,
        created_at=note.created_at,
        updated_at=note.updated_at,
        items=[_to_item_record(item) for item in note.items],
    )


def _sqlite_path_from_engine(target_engine: Engine) -> Path | None:
    db_file = target_engine.url.database
    if not db_file or db_file == ":memory:":
        return None
    return Path(db_file)


def _backup_sqlite_database(db_path: Path) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    backup_path = db_path.with_name(f"{db_path.name}.bak-{stamp}")
    counter = 1
    while backup_path.exists():
        backup_path = db_path.with_name(f"{db_path.name}.bak-{stamp}-{counter}")
        counter += 1
    with sqlite3.connect(str(db_path)) as src, sqlite3.connect(str(backup_path)) as dst:
        src.backup(dst)
    return backup_path


def _migrate_legacy_single_user_db(
    db_path: Path,
    *,
    admin_username: str,
    admin_password_hash: str,
    legacy_api_token: str = "",
) -> bool:
    """Safely migrate a legacy single-user SQLite DB (user_version == 0) to
    schema version 1 using SQLite's 12-step table-rebuild procedure on a raw
    sqlite3 connection with foreign_keys=OFF outside BEGIN IMMEDIATE."""
    if not db_path.exists():
        return False

    conn = sqlite3.connect(str(db_path), isolation_level=None)
    try:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        if version >= SCHEMA_VERSION:
            return False

        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        if "question" not in tables:
            return False

        question_cols = {
            row[1] for row in conn.execute("PRAGMA table_info(question)").fetchall()
        }
        if "user_id" in question_cols:
            conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            return False

        if not admin_username or not admin_password_hash:
            raise RuntimeError(
                "Legacy database migration requires admin_username and "
                "admin_password_hash in config.toml or DICTIONARY_ADMIN_* env vars."
            )

        backup_path = _backup_sqlite_database(db_path)
        logger.info("Created WAL-safe pre-migration backup at %s", backup_path)

        now = int(time.time())
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute("BEGIN IMMEDIATE")
        try:
            # Re-check inside exclusive write lock to avoid multi-worker races.
            if conn.execute("PRAGMA user_version").fetchone()[0] >= SCHEMA_VERSION:
                conn.execute("ROLLBACK")
                return False

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS user (
                    id INTEGER NOT NULL PRIMARY KEY,
                    username VARCHAR COLLATE NOCASE NOT NULL UNIQUE,
                    password_hash VARCHAR NOT NULL,
                    is_admin BOOLEAN NOT NULL DEFAULT 0,
                    is_active BOOLEAN NOT NULL DEFAULT 1,
                    session_version INTEGER NOT NULL DEFAULT 1,
                    last_review_question_id INTEGER,
                    created_at INTEGER NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS api_token (
                    id INTEGER NOT NULL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES user (id) ON DELETE CASCADE,
                    label VARCHAR NOT NULL DEFAULT 'Chrome Extension',
                    token_hash VARCHAR NOT NULL UNIQUE,
                    created_at INTEGER NOT NULL,
                    last_used_at INTEGER
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS ix_api_token_user_id ON api_token (user_id)"
            )
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_api_token_token_hash ON api_token (token_hash)"
            )

            last_review_qid = None
            if "global_state" in tables:
                row = conn.execute(
                    "SELECT last_review_question_id FROM global_state WHERE id = 1"
                ).fetchone()
                if row:
                    last_review_qid = row[0]

            existing_admin = conn.execute(
                "SELECT id FROM user WHERE is_admin = 1 ORDER BY id ASC LIMIT 1"
            ).fetchone()
            if existing_admin:
                admin_id = existing_admin[0]
            else:
                cur = conn.execute(
                    """
                    INSERT INTO user (
                        username, password_hash, is_admin, is_active,
                        session_version, last_review_question_id, created_at
                    ) VALUES (?, ?, 1, 1, 1, ?, ?)
                    """,
                    (admin_username, admin_password_hash, last_review_qid, now),
                )
                admin_id = cur.lastrowid

            if legacy_api_token:
                token_digest = hash_token(legacy_api_token)
                conn.execute(
                    """
                    INSERT OR IGNORE INTO api_token (
                        user_id, label, token_hash, created_at, last_used_at
                    ) VALUES (?, ?, ?, ?, NULL)
                    """,
                    (admin_id, "Migrated from config", token_digest, now),
                )

            # Rebuild question table with user_id + UNIQUE(user_id, text).
            conn.execute(
                """
                CREATE TABLE question_new (
                    id INTEGER NOT NULL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES user (id) ON DELETE CASCADE,
                    text VARCHAR NOT NULL,
                    example VARCHAR,
                    is_hidden BOOLEAN NOT NULL DEFAULT 0,
                    visit_count INTEGER DEFAULT 0,
                    last_visit INTEGER,
                    last_review INTEGER,
                    CONSTRAINT uq_question_user_text UNIQUE (user_id, text)
                )
                """
            )
            conn.execute(
                """
                INSERT INTO question_new (
                    id, user_id, text, example, is_hidden,
                    visit_count, last_visit, last_review
                )
                SELECT
                    id, ?, text, example, COALESCE(is_hidden, 0),
                    COALESCE(visit_count, 0), last_visit, last_review
                FROM question
                """,
                (admin_id,),
            )
            conn.execute("DROP TABLE question")
            conn.execute("ALTER TABLE question_new RENAME TO question")
            conn.execute(
                "CREATE INDEX ix_question_user_id_id ON question (user_id, id)"
            )

            # Rebuild page_note table with user_id + UNIQUE(user_id, url) if present.
            if "page_note" in tables:
                pn_cols = {
                    row[1]
                    for row in conn.execute("PRAGMA table_info(page_note)").fetchall()
                }
                if "user_id" not in pn_cols:
                    conn.execute(
                        """
                        CREATE TABLE page_note_new (
                            id INTEGER NOT NULL PRIMARY KEY,
                            user_id INTEGER NOT NULL REFERENCES user (id) ON DELETE CASCADE,
                            url VARCHAR NOT NULL,
                            title VARCHAR NOT NULL DEFAULT '',
                            notes_md VARCHAR NOT NULL DEFAULT '',
                            created_at INTEGER NOT NULL,
                            updated_at INTEGER NOT NULL,
                            CONSTRAINT uq_page_note_user_url UNIQUE (user_id, url)
                        )
                        """
                    )
                    conn.execute(
                        """
                        INSERT INTO page_note_new (
                            id, user_id, url, title, notes_md, created_at, updated_at
                        )
                        SELECT id, ?, url, title, notes_md, created_at, updated_at
                        FROM page_note
                        """,
                        (admin_id,),
                    )
                    conn.execute("DROP TABLE page_note")
                    conn.execute("ALTER TABLE page_note_new RENAME TO page_note")

            conn.execute("DROP TABLE IF EXISTS global_state")

            fk_errors = conn.execute("PRAGMA foreign_key_check").fetchall()
            if fk_errors:
                raise RuntimeError(
                    f"Foreign key integrity check failed during migration: {fk_errors}"
                )

            conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            conn.execute("COMMIT")
            logger.info("Migrated legacy single-user database to schema v%d", SCHEMA_VERSION)
            return True
        except Exception:
            conn.execute("ROLLBACK")
            raise
        finally:
            conn.execute("PRAGMA foreign_keys = ON")
    finally:
        conn.close()


def create_tables(target_engine: Engine | None = None) -> None:
    eng = target_engine or engine
    Base.metadata.create_all(eng)
    with eng.begin() as conn:
        current_version = conn.exec_driver_sql("PRAGMA user_version").scalar() or 0
        if current_version < SCHEMA_VERSION:
            conn.exec_driver_sql(f"PRAGMA user_version = {SCHEMA_VERSION}")


def bootstrap_database(
    *,
    admin_username: str = "",
    admin_password_hash: str = "",
    legacy_api_token: str = "",
    target_engine: Engine | None = None,
) -> UserRecord | None:
    """Run any needed legacy migration, ensure tables exist, and seed the initial
    admin user (and legacy API token) if the user table is empty."""
    eng = target_engine or engine
    db_path = _sqlite_path_from_engine(eng)
    if db_path is not None:
        migrated = _migrate_legacy_single_user_db(
            db_path,
            admin_username=admin_username,
            admin_password_hash=admin_password_hash,
            legacy_api_token=legacy_api_token,
        )
        if migrated:
            eng.dispose()

    create_tables(eng)

    with Session(eng) as session:
        existing_admin = (
            session.query(User)
            .filter(User.is_admin == True)
            .order_by(User.id.asc())
            .first()
        )
        if existing_admin is not None:
            if admin_username or admin_password_hash:
                logger.info(
                    "Users already exist in database; bootstrap admin credentials "
                    "in config/env are ignored after initial setup."
                )
            if legacy_api_token:
                logger.info(
                    "Legacy auth.api_token / DICTIONARY_API_TOKEN is ignored after "
                    "bootstrap; manage API tokens in /account."
                )
            return _to_user_record(existing_admin)

        user_count = session.query(func.count(User.id)).scalar() or 0
        if user_count > 0:
            return None

        if not admin_username or not admin_password_hash:
            raise RuntimeError(
                "No users exist in the database. Configure admin_username and "
                "admin_password_hash in config.toml or DICTIONARY_ADMIN_* env vars "
                "for initial bootstrap."
            )

        now = int(time.time())
        admin = User(
            username=admin_username,
            password_hash=admin_password_hash,
            is_admin=True,
            is_active=True,
            session_version=1,
            created_at=now,
        )
        session.add(admin)
        session.flush()
        if legacy_api_token:
            session.add(
                ApiToken(
                    user_id=admin.id,
                    label="Migrated from config",
                    token_hash=hash_token(legacy_api_token),
                    created_at=now,
                )
            )
        session.commit()
        return _to_user_record(admin)


# ---------------------------------------------------------------------------
# Users, API tokens, invites, and password resets
# ---------------------------------------------------------------------------


def db_count_users() -> int:
    with Session(engine) as session:
        return session.query(func.count(User.id)).scalar() or 0


def db_count_active_admins() -> int:
    with Session(engine) as session:
        return (
            session.query(func.count(User.id))
            .filter(User.is_admin == True, User.is_active == True)
            .scalar()
            or 0
        )


def db_get_user_by_id(user_id: int) -> UserRecord | None:
    with Session(engine) as session:
        user = session.get(User, user_id)
        return _to_user_record(user) if user else None


def db_get_user_by_username(username: str) -> UserRecord | None:
    with Session(engine) as session:
        user = session.query(User).filter(User.username == username.strip()).first()
        return _to_user_record(user) if user else None


def db_get_user_with_password_by_username(
    username: str,
) -> tuple[UserRecord, str] | None:
    with Session(engine) as session:
        user = session.query(User).filter(User.username == username.strip()).first()
        if not user:
            return None
        return _to_user_record(user), user.password_hash


def db_list_users_for_admin() -> list[UserAdminSummary]:
    with Session(engine) as session:
        counts = dict(
            session.query(Entry.user_id, func.count(Entry.id))
            .filter(Entry.is_hidden == False)
            .group_by(Entry.user_id)
            .all()
        )
        users = session.query(User).order_by(User.id.asc()).all()
        return [
            UserAdminSummary(
                id=u.id,
                username=u.username,
                is_admin=bool(u.is_admin),
                is_active=bool(u.is_active),
                created_at=u.created_at,
                entry_count=counts.get(u.id, 0),
            )
            for u in users
        ]


def db_create_user(
    username: str, password_hash: str, *, is_admin: bool = False
) -> UserRecord:
    now = int(time.time())
    with Session(engine) as session:
        user = User(
            username=username.strip(),
            password_hash=password_hash,
            is_admin=is_admin,
            is_active=True,
            session_version=1,
            created_at=now,
        )
        session.add(user)
        session.commit()
        return _to_user_record(user)


def db_update_user_password(
    user_id: int, new_password_hash: str
) -> UserRecord | None:
    now = int(time.time())
    with Session(engine) as session:
        user = session.get(User, user_id)
        if not user:
            return None
        user.password_hash = new_password_hash
        user.session_version += 1
        # Invalidate any outstanding unused password reset tokens for this user.
        session.execute(
            update(PasswordResetToken)
            .where(
                PasswordResetToken.user_id == user_id,
                PasswordResetToken.used_at.is_(None),
            )
            .values(used_at=now)
        )
        session.commit()
        return _to_user_record(user)


def db_set_user_active(user_id: int, is_active: bool) -> UserRecord | None:
    with Session(engine) as session:
        user = session.get(User, user_id)
        if not user:
            return None
        user.is_active = is_active
        if not is_active:
            user.session_version += 1
        session.commit()
        return _to_user_record(user)


def db_create_api_token(
    user_id: int, label: str, token_hash: str
) -> ApiTokenRecord:
    now = int(time.time())
    clean_label = label.strip() or "Chrome Extension"
    with Session(engine) as session:
        token = ApiToken(
            user_id=user_id,
            label=clean_label[:64],
            token_hash=token_hash,
            created_at=now,
        )
        session.add(token)
        session.commit()
        return _to_api_token_record(token)


def db_list_api_tokens(user_id: int) -> list[ApiTokenRecord]:
    with Session(engine) as session:
        tokens = (
            session.query(ApiToken)
            .filter(ApiToken.user_id == user_id)
            .order_by(ApiToken.id.desc())
            .all()
        )
        return [_to_api_token_record(t) for t in tokens]


def db_revoke_api_token(user_id: int, token_id: int) -> bool:
    with Session(engine) as session:
        deleted = (
            session.query(ApiToken)
            .filter(ApiToken.id == token_id, ApiToken.user_id == user_id)
            .delete()
        )
        session.commit()
        return deleted > 0


def db_get_user_by_api_token_hash(token_hash: str) -> UserRecord | None:
    now = int(time.time())
    with Session(engine) as session:
        row = (
            session.query(ApiToken, User)
            .join(User, ApiToken.user_id == User.id)
            .filter(ApiToken.token_hash == token_hash)
            .first()
        )
        if not row:
            return None
        token, user = row
        if not user.is_active:
            return None
        if token.last_used_at is None or now - token.last_used_at >= 60:
            token.last_used_at = now
            session.commit()
        return _to_user_record(user)


def db_create_invite_token(
    created_by_user_id: int, token_hash: str, note: str, expires_at: int
) -> InviteTokenRecord:
    now = int(time.time())
    with Session(engine) as session:
        invite = InviteToken(
            token_hash=token_hash,
            note=note.strip()[:100],
            created_by_user_id=created_by_user_id,
            created_at=now,
            expires_at=expires_at,
        )
        session.add(invite)
        session.commit()
        return InviteTokenRecord(
            id=invite.id,
            note=invite.note,
            created_at=invite.created_at,
            expires_at=invite.expires_at,
            used_at=invite.used_at,
            used_by_username=None,
        )


def db_list_invite_tokens(limit: int = 50) -> list[InviteTokenRecord]:
    with Session(engine) as session:
        rows = (
            session.query(InviteToken, User.username)
            .outerjoin(User, InviteToken.used_by_user_id == User.id)
            .order_by(InviteToken.id.desc())
            .limit(limit)
            .all()
        )
        return [
            InviteTokenRecord(
                id=invite.id,
                note=invite.note,
                created_at=invite.created_at,
                expires_at=invite.expires_at,
                used_at=invite.used_at,
                used_by_username=used_username,
            )
            for invite, used_username in rows
        ]


def db_revoke_invite_token(invite_id: int) -> bool:
    with Session(engine) as session:
        deleted = (
            session.query(InviteToken)
            .filter(InviteToken.id == invite_id, InviteToken.used_at.is_(None))
            .delete()
        )
        session.commit()
        return deleted > 0


def db_get_valid_invite_token(
    token_hash: str, now: int | None = None
) -> InviteTokenRecord | None:
    current_time = int(time.time()) if now is None else now
    with Session(engine) as session:
        invite = (
            session.query(InviteToken)
            .filter(
                InviteToken.token_hash == token_hash,
                InviteToken.used_at.is_(None),
                InviteToken.expires_at > current_time,
            )
            .first()
        )
        if not invite:
            return None
        return InviteTokenRecord(
            id=invite.id,
            note=invite.note,
            created_at=invite.created_at,
            expires_at=invite.expires_at,
            used_at=invite.used_at,
            used_by_username=None,
        )


def db_redeem_invite_and_create_user(
    token_hash: str,
    username: str,
    password_hash: str,
    now: int | None = None,
) -> tuple[UserRecord | None, str | None]:
    """Atomically redeem a one-time invite token and create the new user."""
    current_time = int(time.time()) if now is None else now
    with Session(engine) as session:
        user = User(
            username=username.strip(),
            password_hash=password_hash,
            is_admin=False,
            is_active=True,
            session_version=1,
            created_at=current_time,
        )
        session.add(user)
        try:
            session.flush()
        except IntegrityError:
            session.rollback()
            return None, "That username is already taken."

        result = session.execute(
            update(InviteToken)
            .where(
                InviteToken.token_hash == token_hash,
                InviteToken.used_at.is_(None),
                InviteToken.expires_at > current_time,
            )
            .values(used_at=current_time, used_by_user_id=user.id)
        )
        if result.rowcount != 1:
            session.rollback()
            return None, "Invite link is invalid, expired, or already used."

        session.commit()
        return _to_user_record(user), None


def db_create_password_reset_token(
    user_id: int, created_by_user_id: int, token_hash: str, expires_at: int
) -> int | None:
    now = int(time.time())
    with Session(engine) as session:
        user = session.get(User, user_id)
        if not user:
            return None
        # Invalidate any prior unused reset tokens for this user.
        session.execute(
            update(PasswordResetToken)
            .where(
                PasswordResetToken.user_id == user_id,
                PasswordResetToken.used_at.is_(None),
            )
            .values(used_at=now)
        )
        token = PasswordResetToken(
            user_id=user_id,
            token_hash=token_hash,
            created_by_user_id=created_by_user_id,
            created_at=now,
            expires_at=expires_at,
        )
        session.add(token)
        session.commit()
        return token.id


def db_get_valid_password_reset_token(
    token_hash: str, now: int | None = None
) -> tuple[int, str] | None:
    current_time = int(time.time()) if now is None else now
    with Session(engine) as session:
        row = (
            session.query(PasswordResetToken, User)
            .join(User, PasswordResetToken.user_id == User.id)
            .filter(
                PasswordResetToken.token_hash == token_hash,
                PasswordResetToken.used_at.is_(None),
                PasswordResetToken.expires_at > current_time,
                User.is_active == True,
            )
            .first()
        )
        if not row:
            return None
        _, user = row
        return user.id, user.username


def db_redeem_password_reset(
    token_hash: str, new_password_hash: str, now: int | None = None
) -> tuple[UserRecord | None, str | None]:
    """Atomically consume a one-time password reset token and update password."""
    current_time = int(time.time()) if now is None else now
    with Session(engine) as session:
        result = session.execute(
            update(PasswordResetToken)
            .where(
                PasswordResetToken.token_hash == token_hash,
                PasswordResetToken.used_at.is_(None),
                PasswordResetToken.expires_at > current_time,
            )
            .values(used_at=current_time)
        )
        if result.rowcount != 1:
            session.rollback()
            return None, "Password reset link is invalid, expired, or already used."

        token = (
            session.query(PasswordResetToken)
            .filter(PasswordResetToken.token_hash == token_hash)
            .first()
        )
        user = session.get(User, token.user_id) if token else None
        if not user or not user.is_active:
            session.rollback()
            return None, "Password reset link is invalid, expired, or already used."

        user.password_hash = new_password_hash
        user.session_version += 1
        session.commit()
        return _to_user_record(user), None


# ---------------------------------------------------------------------------
# User-scoped entries, definitions, quizzes, and review bookmarks
# ---------------------------------------------------------------------------


def db_get_all_entries(user_id: int):
    with Session(engine) as session:
        return (
            session.query(Entry)
            .filter(Entry.user_id == user_id, Entry.is_hidden == False)
            .order_by(Entry.id.desc())
            .all()
        )


def db_get_quiz_source_entries(user_id: int) -> list[tuple[int, str, str | None]]:
    """Lightweight column-only fetch for building a user's quiz pool without
    joined-loading Definition rows."""
    with Session(engine) as session:
        rows = (
            session.query(Entry.id, Entry.text, Entry.example)
            .filter(Entry.user_id == user_id, Entry.is_hidden == False)
            .all()
        )
        return [(row.id, row.text, row.example) for row in rows]


def db_get_entry_visit_stats(user_id: int) -> dict[int, tuple[int, int | None]]:
    """Return {entry_id: (visit_count, last_visit)} for all active entries of user."""
    with Session(engine) as session:
        rows = (
            session.query(Entry.id, Entry.visit_count, Entry.last_visit)
            .filter(Entry.user_id == user_id, Entry.is_hidden == False)
            .all()
        )
        return {row.id: (row.visit_count or 0, row.last_visit) for row in rows}


ENTRIES_PAGE_SIZE = 200


def db_count_entries(user_id: int) -> int:
    with Session(engine) as session:
        return (
            session.query(func.count(Entry.id))
            .filter(Entry.user_id == user_id, Entry.is_hidden == False)
            .scalar()
            or 0
        )


def db_get_entry_page_number(
    user_id: int, entry_id: int, page_size: int = ENTRIES_PAGE_SIZE
) -> int | None:
    """Which page (1-indexed) `entry_id` falls on in the default, unfiltered,
    newest-first /entries listing. Returns None if the entry doesn't exist,
    belongs to another user, or is hidden."""
    with Session(engine) as session:
        entry = (
            session.query(Entry)
            .filter(
                Entry.id == entry_id,
                Entry.user_id == user_id,
                Entry.is_hidden == False,
            )
            .first()
        )
        if not entry:
            return None
        rank = (
            session.query(func.count(Entry.id))
            .filter(Entry.user_id == user_id, Entry.is_hidden == False)
            .filter(Entry.id > entry_id)
            .scalar()
        )
        return rank // page_size + 1


def db_get_entries_page(
    user_id: int,
    query: str = "",
    include_examples: bool = False,
    page: int = 1,
    page_size: int = ENTRIES_PAGE_SIZE,
) -> tuple[list[EntrySummary], int]:
    """Return (entries for this page, total matching count), newest first."""
    with Session(engine) as session:
        columns = [Entry.id, Entry.text, Entry.visit_count]
        if include_examples:
            columns.append(Entry.example)

        base_query = session.query(*columns).filter(
            Entry.user_id == user_id, Entry.is_hidden == False
        )

        query = query.strip()
        if query:
            escaped_query = (
                query.replace("\\", "\\\\")
                .replace("%", "\\%")
                .replace("_", "\\_")
            )
            like_pattern = f"%{escaped_query}%"
            base_query = base_query.filter(
                or_(
                    Entry.text.ilike(like_pattern, escape="\\"),
                    Entry.example.ilike(like_pattern, escape="\\"),
                )
            )

        total = base_query.order_by(None).count()

        page = max(page, 1)
        rows = (
            base_query.order_by(Entry.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )

        if include_examples:
            entries = [
                EntrySummary(
                    id=row.id,
                    text=row.text,
                    visit_count=row.visit_count or 0,
                    example=row.example,
                )
                for row in rows
            ]
        else:
            entries = [
                EntrySummary(
                    id=row.id,
                    text=row.text,
                    visit_count=row.visit_count or 0,
                )
                for row in rows
            ]

        return entries, total


def db_count_entries_visited_since(user_id: int, cutoff_timestamp: int) -> int:
    with Session(engine) as session:
        return (
            session.query(Entry)
            .filter(Entry.user_id == user_id, Entry.is_hidden == False)
            .filter(Entry.last_visit != None)
            .filter(Entry.last_visit >= cutoff_timestamp)
            .count()
        )


def db_get_entry_by_id(user_id: int, entry_id: int):
    with Session(engine) as session:
        return (
            session.query(Entry)
            .filter(Entry.id == entry_id, Entry.user_id == user_id)
            .first()
        )


def db_get_entry_by_text(user_id: int, entry_text: str):
    with Session(engine) as session:
        return (
            session.query(Entry)
            .filter(Entry.user_id == user_id, Entry.text == entry_text)
            .first()
        )


def db_delete_entry(user_id: int, entry_id: int) -> bool:
    with Session(engine) as session:
        deleted = (
            session.query(Entry)
            .filter(Entry.id == entry_id, Entry.user_id == user_id)
            .delete()
        )
        if deleted > 0:
            session.execute(
                update(User)
                .where(
                    User.id == user_id,
                    User.last_review_question_id == entry_id,
                )
                .values(last_review_question_id=None)
            )
        session.commit()
        return deleted > 0


def db_update_entry_text(user_id: int, entry_id: int, text: str):
    with Session(engine) as session:
        entry = (
            session.query(Entry)
            .filter(Entry.id == entry_id, Entry.user_id == user_id)
            .first()
        )
        if entry:
            entry.text = text
            session.commit()
            return entry.id
    return None


def db_update_example(user_id: int, entry_id: int, example_text: str):
    with Session(engine) as session:
        entry = (
            session.query(Entry)
            .filter(Entry.id == entry_id, Entry.user_id == user_id)
            .first()
        )
        if entry:
            entry.example = example_text
            session.commit()
            return entry.id
    return None


def db_add_entry(
    user_id: int,
    text: str,
    definition_text: str = "",
    example_text: str = "",
):
    with Session(engine) as session:
        text = text.strip()
        clean_definition = definition_text.strip()
        clean_example = example_text.strip() or None
        entry = Entry(
            user_id=user_id,
            text=text,
            example=clean_example,
            last_visit=int(time.time()),
        )
        if clean_definition:
            entry.definitions.append(Definition(text=clean_definition))
        session.add(entry)
        session.commit()
        return entry.id


VISIT_COOLDOWN_SECONDS = 3600 * 12


def db_record_entry_visit(
    user_id: int, entry_id: int, now: int | None = None
) -> bool | None:
    """Record a visit if at least 12h have elapsed since last_visit (or it was
    never visited). Returns True if recorded, False if still in cooldown, or
    None if the entry does not exist (or belongs to another user or is hidden)."""
    current_time = int(time.time()) if now is None else now
    with Session(engine) as session:
        entry = (
            session.query(Entry)
            .options(noload(Entry.definitions))
            .filter(
                Entry.id == entry_id,
                Entry.user_id == user_id,
                Entry.is_hidden == False,
            )
            .first()
        )
        if not entry:
            return None
        if (
            entry.last_visit is None
            or current_time - entry.last_visit >= VISIT_COOLDOWN_SECONDS
        ):
            entry.last_visit = current_time
            entry.visit_count = (entry.visit_count or 0) + 1
            session.commit()
            return True
        return False


def db_get_definition_by_id(user_id: int, definition_id: int):
    with Session(engine) as session:
        return (
            session.query(Definition)
            .join(Entry, Definition.question_id == Entry.id)
            .filter(Definition.id == definition_id, Entry.user_id == user_id)
            .first()
        )


def db_delete_definition(user_id: int, definition_id: int):
    with Session(engine) as session:
        definition = (
            session.query(Definition)
            .join(Entry, Definition.question_id == Entry.id)
            .filter(Definition.id == definition_id, Entry.user_id == user_id)
            .first()
        )
        if definition:
            entry_id = definition.question_id
            session.delete(definition)
            session.commit()
            return entry_id
    return None


def db_update_definition_text(user_id: int, definition_id: int, text: str):
    with Session(engine) as session:
        definition = (
            session.query(Definition)
            .join(Entry, Definition.question_id == Entry.id)
            .filter(Definition.id == definition_id, Entry.user_id == user_id)
            .first()
        )
        if definition:
            entry_id = definition.question_id
            definition.text = text
            session.commit()
            return entry_id
    return None


def db_add_definition(user_id: int, entry_id: int, text: str) -> int | None:
    with Session(engine) as session:
        entry = (
            session.query(Entry)
            .options(noload(Entry.definitions))
            .filter(Entry.id == entry_id, Entry.user_id == user_id)
            .first()
        )
        if not entry:
            return None
        definition = Definition(text=text.strip(), question_id=entry.id)
        session.add(definition)
        session.commit()
        return definition.id


def db_set_review_bookmark(user_id: int, entry_id: int) -> bool:
    with Session(engine) as session:
        entry = (
            session.query(Entry)
            .options(noload(Entry.definitions))
            .filter(Entry.id == entry_id, Entry.user_id == user_id)
            .first()
        )
        if not entry:
            return False
        user = session.get(User, user_id)
        if not user:
            return False
        user.last_review_question_id = entry_id
        session.commit()
        return True


def db_clear_review_bookmark(user_id: int, entry_id: int) -> bool:
    with Session(engine) as session:
        user = session.get(User, user_id)
        if not user:
            return False
        if user.last_review_question_id == entry_id:
            user.last_review_question_id = None
            session.commit()
        return True


def get_review_bookmark(user_id: int) -> int | None:
    with Session(engine) as session:
        user = session.get(User, user_id)
        return user.last_review_question_id if user else None


def db_get_entries_by_ids(
    user_id: int, entry_ids: list[int]
) -> list[EntrySummary]:
    if not entry_ids:
        return []
    with Session(engine) as session:
        rows = (
            session.query(Entry.id, Entry.text, Entry.visit_count)
            .filter(
                Entry.user_id == user_id,
                Entry.is_hidden == False,
                Entry.id.in_(entry_ids),
            )
            .all()
        )
        by_id = {
            row.id: EntrySummary(
                id=row.id, text=row.text, visit_count=row.visit_count or 0
            )
            for row in rows
        }
        return [by_id[eid] for eid in entry_ids if eid in by_id]


# ---------------------------------------------------------------------------
# User-scoped page notes and capture items (/inbox & /api/v1/*)
# ---------------------------------------------------------------------------


def _upsert_page_note_row(
    session: Session,
    user_id: int,
    normalized_url: str,
    title: str,
    now: int,
    notes_md: str | None = None,
) -> PageNote:
    clean_title = title.strip()
    stmt = sqlite_insert(PageNote).values(
        user_id=user_id,
        url=normalized_url,
        title=clean_title,
        notes_md="" if notes_md is None else notes_md,
        created_at=now,
        updated_at=now,
    )
    update_values: dict[str, object] = {"updated_at": now}
    if clean_title:
        update_values["title"] = clean_title
    if notes_md is not None:
        update_values["notes_md"] = notes_md
    stmt = stmt.on_conflict_do_update(
        index_elements=[PageNote.user_id, PageNote.url], set_=update_values
    )
    session.execute(stmt)
    return (
        session.query(PageNote)
        .options(joinedload(PageNote.items))
        .filter(PageNote.user_id == user_id, PageNote.url == normalized_url)
        .one()
    )


def db_get_page_note_by_url(
    user_id: int, normalized_url: str
) -> PageNoteRecord | None:
    with Session(engine) as session:
        note = (
            session.query(PageNote)
            .options(joinedload(PageNote.items))
            .filter(PageNote.user_id == user_id, PageNote.url == normalized_url)
            .first()
        )
        return _to_page_note_record(note) if note else None


def db_list_page_notes(user_id: int, limit: int = 100) -> list[PageNoteRecord]:
    with Session(engine) as session:
        notes = (
            session.query(PageNote)
            .options(joinedload(PageNote.items))
            .filter(PageNote.user_id == user_id)
            .order_by(PageNote.updated_at.desc(), PageNote.id.desc())
            .limit(limit)
            .all()
        )
        return [_to_page_note_record(note) for note in notes]


def db_upsert_page_note(
    user_id: int, normalized_url: str, title: str, notes_md: str
) -> PageNoteRecord | None:
    now = int(time.time())
    with Session(engine) as session:
        if not notes_md.strip():
            existing = (
                session.query(PageNote)
                .options(joinedload(PageNote.items))
                .filter(
                    PageNote.user_id == user_id, PageNote.url == normalized_url
                )
                .first()
            )
            if not existing:
                return None
            if not existing.items:
                session.delete(existing)
                session.commit()
                return None
            existing.notes_md = ""
            if title.strip():
                existing.title = title.strip()
            existing.updated_at = now
            session.commit()
            return _to_page_note_record(existing)

        note = _upsert_page_note_row(
            session, user_id, normalized_url, title, now, notes_md=notes_md
        )
        session.commit()
        return _to_page_note_record(note)


def db_add_capture_item(
    user_id: int,
    normalized_url: str,
    title: str,
    word: str,
    context: str = "",
    definition_text: str = "",
    timestamp_seconds: int | None = None,
) -> tuple[PageNoteRecord, CaptureItemRecord]:
    now = int(time.time())
    with Session(engine) as session:
        note = _upsert_page_note_row(session, user_id, normalized_url, title, now)
        item = PageCaptureItem(
            page_note_id=note.id,
            word=word.strip(),
            context=context.strip(),
            definition_text=definition_text.strip(),
            timestamp_seconds=timestamp_seconds,
            created_at=now,
        )
        session.add(item)
        note.updated_at = now
        session.commit()
        session.refresh(note)
        return _to_page_note_record(note), _to_item_record(item)


def db_update_capture_item(
    user_id: int,
    item_id: int,
    *,
    word: str | None = None,
    context: str | None = None,
    definition_text: str | None = None,
) -> CaptureItemRecord | None:
    now = int(time.time())
    with Session(engine) as session:
        row = (
            session.query(PageCaptureItem, PageNote)
            .join(PageNote, PageCaptureItem.page_note_id == PageNote.id)
            .filter(PageCaptureItem.id == item_id, PageNote.user_id == user_id)
            .first()
        )
        if not row:
            return None
        item, note = row
        if word is not None:
            item.word = word.strip()
        if context is not None:
            item.context = context.strip()
        if definition_text is not None:
            item.definition_text = definition_text.strip()
        note.updated_at = now
        session.commit()
        return _to_item_record(item)


def db_delete_capture_item(user_id: int, item_id: int) -> bool:
    now = int(time.time())
    with Session(engine) as session:
        row = (
            session.query(PageCaptureItem, PageNote)
            .join(PageNote, PageCaptureItem.page_note_id == PageNote.id)
            .filter(PageCaptureItem.id == item_id, PageNote.user_id == user_id)
            .first()
        )
        if not row:
            return False
        item, note = row
        page_note_id = note.id
        session.delete(item)
        session.flush()
        refreshed = (
            session.query(PageNote)
            .options(joinedload(PageNote.items))
            .filter(PageNote.id == page_note_id, PageNote.user_id == user_id)
            .first()
        )
        if refreshed:
            if not refreshed.notes_md.strip() and not refreshed.items:
                session.delete(refreshed)
            else:
                refreshed.updated_at = now
        session.commit()
        return True


def db_delete_page_note(user_id: int, note_id: int) -> bool:
    with Session(engine) as session:
        note = (
            session.query(PageNote)
            .filter(PageNote.id == note_id, PageNote.user_id == user_id)
            .first()
        )
        if not note:
            return False
        session.delete(note)
        session.commit()
        return True


def db_clear_promoted_items(user_id: int, note_id: int | None = None) -> int:
    now = int(time.time())
    with Session(engine) as session:
        query = (
            session.query(PageCaptureItem)
            .join(PageNote, PageCaptureItem.page_note_id == PageNote.id)
            .filter(
                PageNote.user_id == user_id,
                PageCaptureItem.promoted_entry_id.is_not(None),
            )
        )
        if note_id is not None:
            query = query.filter(PageCaptureItem.page_note_id == note_id)
        items = query.all()
        if not items:
            return 0
        affected_note_ids = {item.page_note_id for item in items}
        for item in items:
            session.delete(item)
        session.flush()
        for affected_id in affected_note_ids:
            note = (
                session.query(PageNote)
                .options(joinedload(PageNote.items))
                .filter(PageNote.id == affected_id, PageNote.user_id == user_id)
                .first()
            )
            if note:
                if not note.notes_md.strip() and not note.items:
                    session.delete(note)
                else:
                    note.updated_at = now
        session.commit()
        return len(items)


def db_promote_capture_items(
    user_id: int, item_ids: list[int], validate_fn
) -> list[dict[str, object]]:
    """Promote captured items into permanent Entry rows for `user_id` using a
    SAVEPOINT per item so a duplicate or validation error on one item never
    aborts the batch."""
    now = int(time.time())
    results: list[dict[str, object]] = []
    with Session(engine) as session:
        for item_id in item_ids:
            item = (
                session.query(PageCaptureItem)
                .join(PageNote, PageCaptureItem.page_note_id == PageNote.id)
                .filter(PageCaptureItem.id == item_id, PageNote.user_id == user_id)
                .first()
            )
            if not item:
                results.append({"item_id": item_id, "status": "not_found"})
                continue
            if item.promoted_entry_id is not None:
                results.append(
                    {
                        "item_id": item_id,
                        "status": "already_promoted",
                        "entry_id": item.promoted_entry_id,
                    }
                )
                continue

            formatted_text, error = validate_fn(item.word, item.context)
            if error or not formatted_text:
                results.append(
                    {
                        "item_id": item_id,
                        "status": "error",
                        "error": error or "Invalid entry",
                    }
                )
                continue

            clean_def = item.definition_text.strip()
            try:
                with session.begin_nested():
                    entry = Entry(
                        user_id=user_id, text=formatted_text, last_visit=now
                    )
                    if clean_def:
                        entry.definitions.append(Definition(text=clean_def))
                    session.add(entry)
                    session.flush()
                    entry_id = entry.id
                item.promoted_entry_id = entry_id
                results.append(
                    {
                        "item_id": item_id,
                        "status": "created",
                        "entry_id": entry_id,
                    }
                )
            except IntegrityError:
                existing = (
                    session.query(Entry)
                    .options(noload(Entry.definitions))
                    .filter(Entry.user_id == user_id, Entry.text == formatted_text)
                    .first()
                )
                if existing:
                    item.promoted_entry_id = existing.id
                    results.append(
                        {
                            "item_id": item_id,
                            "status": "duplicate",
                            "entry_id": existing.id,
                        }
                    )
                else:
                    results.append(
                        {
                            "item_id": item_id,
                            "status": "error",
                            "error": "Entry already exists.",
                        }
                    )
        session.commit()
    return results


def main():
    parser = ArgumentParser(description="Database utility for Glossbook")

    subparsers = parser.add_subparsers(dest="mode", help="Mode selection")
    subparsers.add_parser("create-table")

    entry_parser = subparsers.add_parser("entry")
    entry_parser.add_argument(
        "--username", required=True, help="Username owning the entry"
    )
    entry_parser.add_argument(
        "--entry", required=True, help="Specify the entry text to look up"
    )

    reset_parser = subparsers.add_parser(
        "reset-password", help="Emergency CLI password reset for a user"
    )
    reset_parser.add_argument(
        "--username", required=True, help="Username to reset password for"
    )

    args = parser.parse_args()

    if args.mode == "entry":
        user = db_get_user_by_username(args.username)
        if not user:
            print(f"User not found: {args.username}")
            return
        entry = db_get_entry_by_text(user.id, args.entry)
        print(entry if entry else "Entry not found")
    elif args.mode == "create-table":
        create_tables()
    elif args.mode == "reset-password":
        from pwdlib import PasswordHash

        user = db_get_user_by_username(args.username)
        if not user:
            print(f"User not found: {args.username}")
            raise SystemExit(1)
        password = getpass.getpass("New password (10-128 chars): ")
        confirm = getpass.getpass("Confirm password: ")
        if password != confirm:
            print("Passwords do not match.")
            raise SystemExit(1)
        if not (10 <= len(password) <= 128):
            print("Password must be between 10 and 128 characters.")
            raise SystemExit(1)
        new_hash = PasswordHash.recommended().hash(password)
        db_update_user_password(user.id, new_hash)
        print(f"Password updated and old sessions invalidated for {user.username}.")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
