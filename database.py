import os
import time
from argparse import ArgumentParser
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import (
    Boolean,
    ForeignKey,
    Integer,
    String,
    create_engine,
    event,
    func,
    or_,
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


@dataclass(frozen=True)
class EntrySummary:
    id: int
    text: str
    visit_count: int
    example: str | None = None


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


class Entry(Base):
    # NOTE: DB table is still named "question" to avoid a migration.
    __tablename__ = "question"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    text: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    definitions: Mapped[list["Definition"]] = relationship(
        "Definition",
        back_populates="entry",
        lazy="joined",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    example: Mapped[str] = mapped_column(String, nullable=True)
    is_hidden: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    visit_count: Mapped[int] = mapped_column(Integer, nullable=True, default=0)
    last_visit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_review: Mapped[int | None] = mapped_column(Integer, nullable=True)

    def __str__(self) -> str:
        return (
            f'Entry(id={self.id}, text="{self.text}",'
            f" definitions={[str(d) for d in self.definitions]})"
            f" example: {self.example}"
        )


class Definition(Base):
    # NOTE: DB table is still named "answer" to avoid a migration.
    __tablename__ = "answer"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    text: Mapped[str] = mapped_column(String, nullable=False)

    # Establish a many-to-one relationship with the Entry table
    # (DB column/table names remain "question").
    question_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("question.id", ondelete="CASCADE")
    )
    entry: Mapped[Entry] = relationship(Entry, back_populates="definitions")

    def __str__(self) -> str:
        return f'Definition(id={self.id}, text="{self.text}"'


class GlobalState(Base):
    __tablename__ = "global_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)

    last_review_question_id: Mapped[int | None] = mapped_column(
        ForeignKey("question.id", ondelete="SET NULL"), nullable=True
    )


class PageNote(Base):
    __tablename__ = "page_note"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    url: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
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
        Integer, ForeignKey("page_note.id", ondelete="CASCADE"), nullable=False, index=True
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


# Emit CREATE TABLE DDL
def create_tables():
    Base.metadata.create_all(
        engine,
    )


def db_get_all_entries():
    with Session(engine) as session:
        entries = (
            session.query(Entry)
            .filter(Entry.is_hidden == False)
            .order_by(Entry.id.desc())
            .all()
        )
        return entries


def db_get_quiz_source_entries() -> list[tuple[int, str, str | None]]:
    """Lightweight column-only fetch for building the quiz pool without
    joined-loading Definition rows."""
    with Session(engine) as session:
        rows = (
            session.query(Entry.id, Entry.text, Entry.example)
            .filter(Entry.is_hidden == False)
            .all()
        )
        return [(row.id, row.text, row.example) for row in rows]


def db_get_entry_visit_stats() -> dict[int, tuple[int, int | None]]:
    """Return {entry_id: (visit_count, last_visit)} for all active entries."""
    with Session(engine) as session:
        rows = (
            session.query(Entry.id, Entry.visit_count, Entry.last_visit)
            .filter(Entry.is_hidden == False)
            .all()
        )
        return {row.id: (row.visit_count or 0, row.last_visit) for row in rows}



ENTRIES_PAGE_SIZE = 200


def db_count_entries() -> int:
    with Session(engine) as session:
        return (
            session.query(func.count(Entry.id))
            .filter(Entry.is_hidden == False)
            .scalar()
        )


def db_get_entry_page_number(
    entry_id: int, page_size: int = ENTRIES_PAGE_SIZE
) -> int | None:
    """Which page (1-indexed) `entry_id` falls on in the default, unfiltered,
    newest-first /entries listing. Returns None if the entry doesn't exist
    or is hidden."""
    with Session(engine) as session:
        entry = (
            session.query(Entry)
            .filter(Entry.id == entry_id, Entry.is_hidden == False)
            .first()
        )
        if not entry:
            return None
        rank = (
            session.query(func.count(Entry.id))
            .filter(Entry.is_hidden == False)
            .filter(Entry.id > entry_id)
            .scalar()
        )
        return rank // page_size + 1


def db_get_entries_page(
    query: str = "",
    include_examples: bool = False,
    page: int = 1,
    page_size: int = ENTRIES_PAGE_SIZE,
) -> tuple[list[EntrySummary], int]:
    """Return (entries for this page, total matching count), newest first.

    `query` is matched case-insensitively against both the entry text
    (word + context) and the example, so it works as a single search box
    over everything a user is likely to remember about an entry.
    """
    with Session(engine) as session:
        columns = [Entry.id, Entry.text, Entry.visit_count]
        if include_examples:
            columns.append(Entry.example)

        base_query = session.query(*columns).filter(Entry.is_hidden == False)

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


def db_count_entries_visited_since(cutoff_timestamp: int) -> int:
    with Session(engine) as session:
        return (
            session.query(Entry)
            .filter(Entry.is_hidden == False)
            .filter(Entry.last_visit != None)
            .filter(Entry.last_visit >= cutoff_timestamp)
            .count()
        )


def db_get_entry_by_id(entry_id: int):
    with Session(engine) as session:
        return session.query(Entry).filter(Entry.id == entry_id).first()


def db_get_entry_by_text(entry_text: str):
    with Session(engine) as session:
        return session.query(Entry).filter(Entry.text == entry_text).first()


def db_delete_entry(entry_id: int) -> bool:
    with Session(engine) as session:
        deleted = session.query(Entry).filter(Entry.id == entry_id).delete()
        session.commit()
        return deleted > 0


def db_update_entry_text(entry_id: int, text: str):
    with Session(engine) as session:
        entry = session.query(Entry).filter(Entry.id == entry_id).first()
        if entry:
            entry.text = text
            session.commit()
            return entry.id


def db_update_example(entry_id: int, example_text: str):
    with Session(engine) as session:
        entry = session.query(Entry).filter(Entry.id == entry_id).first()
        if entry:
            entry.example = example_text
            session.commit()
            return entry.id


def db_add_entry(
    text: str, definition_text: str = "", example_text: str = ""
):
    with Session(engine) as session:
        text = text.strip()
        clean_definition = definition_text.strip()
        clean_example = example_text.strip() or None
        entry = Entry(
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


def db_record_entry_visit(entry_id: int, now: int | None = None) -> bool | None:
    """Record a visit if at least 12h have elapsed since last_visit (or it was
    never visited). Returns True if recorded, False if still in cooldown, or
    None if the entry does not exist (or is hidden)."""
    current_time = int(time.time()) if now is None else now
    with Session(engine) as session:
        entry = (
            session.query(Entry)
            .options(noload(Entry.definitions))
            .filter(Entry.id == entry_id, Entry.is_hidden == False)
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


def db_entry_last_visit_old_enough(entry_id: int):
    with Session(engine) as session:
        entry = (
            session.query(Entry)
            .options(noload(Entry.definitions))
            .filter(Entry.id == entry_id)
            .first()
        )
        if entry:
            last_visit = entry.last_visit
            if not last_visit:
                entry.last_visit = int(time.time())
                session.commit()
                return True
            now = int(time.time())
            # last visit more than 12h ago
            if now - last_visit >= VISIT_COOLDOWN_SECONDS:
                entry.last_visit = now
                session.commit()
                return True
            return False


def db_entry_increment_visit_count(entry_id: int):
    with Session(engine) as session:
        entry = (
            session.query(Entry)
            .options(noload(Entry.definitions))
            .filter(Entry.id == entry_id)
            .first()
        )
        if entry:
            entry.visit_count = (entry.visit_count or 0) + 1
            session.commit()
            return True


def db_get_definition_by_id(definition_id: int):
    with Session(engine) as session:
        return (
            session.query(Definition)
            .filter(Definition.id == definition_id)
            .first()
        )


def db_delete_definition(definition_id: int):
    with Session(engine) as session:
        definition = (
            session.query(Definition)
            .filter(Definition.id == definition_id)
            .first()
        )
        if definition:
            entry_id = definition.question_id
            session.query(Definition).filter(
                Definition.id == definition_id
            ).delete()
            session.commit()
            return entry_id


def db_update_definition_text(definition_id: int, text: str):
    with Session(engine) as session:
        definition = (
            session.query(Definition)
            .filter(Definition.id == definition_id)
            .first()
        )
        if definition:
            entry_id = definition.question_id
            definition.text = text
            session.commit()
            return entry_id


def db_add_definition(text: str, entry: Entry):
    with Session(engine) as session:
        text = text.strip()
        definition = Definition(text=text, entry=entry)
        session.add(definition)
        session.commit()
        return definition.id


def db_set_review_bookmark(entry_id: int):
    with Session(engine) as session:
        entry = session.query(Entry).filter(Entry.id == entry_id).first()
        if entry:
            state = session.get(GlobalState, 1)
            if state is None:
                state = GlobalState(id=1)
                session.add(state)
            state.last_review_question_id = entry_id
            session.commit()
            return True
    return False


def db_clear_review_bookmark(entry_id: int):
    with Session(engine) as session:
        state = session.get(GlobalState, 1)
        if state and state.last_review_question_id == entry_id:
            state.last_review_question_id = None
            session.commit()
        return True


def get_review_bookmark() -> int | None:
    with Session(engine) as session:
        state = session.get(GlobalState, 1)
        return state.last_review_question_id if state else None


def db_get_entries_by_ids(entry_ids: list[int]) -> list[EntrySummary]:
    if not entry_ids:
        return []
    with Session(engine) as session:
        rows = (
            session.query(Entry.id, Entry.text, Entry.visit_count)
            .filter(Entry.is_hidden == False, Entry.id.in_(entry_ids))
            .all()
        )
        by_id = {
            row.id: EntrySummary(
                id=row.id, text=row.text, visit_count=row.visit_count or 0
            )
            for row in rows
        }
        return [by_id[eid] for eid in entry_ids if eid in by_id]


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


def _upsert_page_note_row(
    session: Session,
    normalized_url: str,
    title: str,
    now: int,
    notes_md: str | None = None,
) -> PageNote:
    clean_title = title.strip()
    stmt = sqlite_insert(PageNote).values(
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
        index_elements=[PageNote.url], set_=update_values
    )
    session.execute(stmt)
    return (
        session.query(PageNote)
        .options(joinedload(PageNote.items))
        .filter(PageNote.url == normalized_url)
        .one()
    )


def db_get_page_note_by_url(normalized_url: str) -> PageNoteRecord | None:
    with Session(engine) as session:
        note = (
            session.query(PageNote)
            .options(joinedload(PageNote.items))
            .filter(PageNote.url == normalized_url)
            .first()
        )
        return _to_page_note_record(note) if note else None


def db_list_page_notes(limit: int = 100) -> list[PageNoteRecord]:
    with Session(engine) as session:
        notes = (
            session.query(PageNote)
            .options(joinedload(PageNote.items))
            .order_by(PageNote.updated_at.desc(), PageNote.id.desc())
            .limit(limit)
            .all()
        )
        return [_to_page_note_record(note) for note in notes]


def db_upsert_page_note(
    normalized_url: str, title: str, notes_md: str
) -> PageNoteRecord | None:
    now = int(time.time())
    with Session(engine) as session:
        if not notes_md.strip():
            existing = (
                session.query(PageNote)
                .options(joinedload(PageNote.items))
                .filter(PageNote.url == normalized_url)
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
            session, normalized_url, title, now, notes_md=notes_md
        )
        session.commit()
        return _to_page_note_record(note)


def db_add_capture_item(
    normalized_url: str,
    title: str,
    word: str,
    context: str = "",
    definition_text: str = "",
    timestamp_seconds: int | None = None,
) -> tuple[PageNoteRecord, CaptureItemRecord]:
    now = int(time.time())
    with Session(engine) as session:
        note = _upsert_page_note_row(session, normalized_url, title, now)
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
    item_id: int,
    *,
    word: str | None = None,
    context: str | None = None,
    definition_text: str | None = None,
) -> CaptureItemRecord | None:
    now = int(time.time())
    with Session(engine) as session:
        item = session.get(PageCaptureItem, item_id)
        if not item:
            return None
        if word is not None:
            item.word = word.strip()
        if context is not None:
            item.context = context.strip()
        if definition_text is not None:
            item.definition_text = definition_text.strip()
        note = session.get(PageNote, item.page_note_id)
        if note:
            note.updated_at = now
        session.commit()
        return _to_item_record(item)


def db_delete_capture_item(item_id: int) -> bool:
    now = int(time.time())
    with Session(engine) as session:
        item = session.get(PageCaptureItem, item_id)
        if not item:
            return False
        page_note_id = item.page_note_id
        session.delete(item)
        session.flush()
        note = (
            session.query(PageNote)
            .options(joinedload(PageNote.items))
            .filter(PageNote.id == page_note_id)
            .first()
        )
        if note:
            if not note.notes_md.strip() and not note.items:
                session.delete(note)
            else:
                note.updated_at = now
        session.commit()
        return True


def db_promote_capture_items(
    item_ids: list[int], validate_fn
) -> list[dict[str, object]]:
    """Promote captured items into permanent Entry rows using a SAVEPOINT per
    item so a duplicate or validation error on one item never aborts the batch."""
    now = int(time.time())
    results: list[dict[str, object]] = []
    with Session(engine) as session:
        for item_id in item_ids:
            item = session.get(PageCaptureItem, item_id)
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
                    entry = Entry(text=formatted_text, last_visit=now)
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
                    .filter(Entry.text == formatted_text)
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
    parser = ArgumentParser(description="Your program's description")

    subparsers = parser.add_subparsers(dest="mode", help="Mode selection")
    subparsers.add_parser("create-table")
    entry_parser = subparsers.add_parser("entry")
    entry_parser.add_argument(
        "--entry", required=True, help="Specify the entry"
    )

    args = parser.parse_args()

    print("Mode:", args.mode)
    if args.mode == "entry":
        print("Entry:", args.entry)
        db_get_entry_by_text(args.entry)
    if args.mode == "create-table":
        create_tables()


if __name__ == "__main__":
    main()
