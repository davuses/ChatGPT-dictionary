import time
from argparse import ArgumentParser
from dataclasses import dataclass

from sqlalchemy import (
    Boolean,
    ForeignKey,
    Integer,
    String,
    create_engine,
    event,
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    mapped_column,
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
    cursor.close()


engine = create_engine(
    "sqlite:///dictionary.db",
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



def db_get_homepage_entries(include_examples: bool = False):
    with Session(engine) as session:
        columns = [Entry.id, Entry.text, Entry.visit_count]
        if include_examples:
            columns.append(Entry.example)

        rows = (
            session.query(*columns)
            .filter(Entry.is_hidden == False)
            .order_by(Entry.id.desc())
            .all()
        )

        if include_examples:
            return [
                EntrySummary(
                    id=row.id,
                    text=row.text,
                    visit_count=row.visit_count or 0,
                    example=row.example,
                )
                for row in rows
            ]

        return [
            EntrySummary(
                id=row.id,
                text=row.text,
                visit_count=row.visit_count or 0,
            )
            for row in rows
        ]


def db_get_entry_by_id(entry_id: int):
    with Session(engine) as session:
        return session.query(Entry).filter(Entry.id == entry_id).first()


def db_get_entry_by_text(entry_text: str):
    with Session(engine) as session:
        return session.query(Entry).filter(Entry.text == entry_text).first()


def db_delete_entry(entry_id: int):
    with Session(engine) as session:
        session.query(Entry).filter(Entry.id == entry_id).delete()
        session.commit()


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


def db_add_entry(text: str):
    with Session(engine) as session:
        text = text.strip()
        entry = Entry(text=text, last_visit=int(time.time()))
        session.add(entry)
        session.commit()
        return entry.id


def db_entry_last_visit_old_enough(entry_id: int):
    with Session(engine) as session:
        entry = session.query(Entry).filter(Entry.id == entry_id).first()
        if entry:
            last_visit = entry.last_visit
            if not last_visit:
                entry.last_visit = int(time.time())
                session.commit()
                return True
            now = int(time.time())
            # last visit more than 12h ago
            if now - last_visit >= 3600 * 12:
                entry.last_visit = now
                session.commit()
                return True
            return False


def db_entry_increment_visit_count(entry_id: int):
    with Session(engine) as session:
        entry = session.query(Entry).filter(Entry.id == entry_id).first()
        if entry:
            entry.visit_count = entry.visit_count + 1
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
