import time
from argparse import ArgumentParser

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
    answers: Mapped[list["Answer"]] = relationship(
        "Answer",
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
            f" answers={[str(a) for a in self.answers]})"
            f" example: {self.example}"
        )


class Answer(Base):
    __tablename__ = "answer"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    text: Mapped[str] = mapped_column(String, nullable=False)

    # Establish a many-to-one relationship with the Entry table
    # (DB column/table names remain "question").
    question_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("question.id", ondelete="CASCADE")
    )
    entry: Mapped[Entry] = relationship(Entry, back_populates="answers")

    def __str__(self) -> str:
        return f'Answer(id={self.id}, text="{self.text}"'


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


def insert_entries_and_answers():
    from mappings import get_question_answer_mappings

    inserted_entry_count = 0
    entries_with_empty_answers = []
    entries_with_multi_answers = []
    with Session(engine) as session:
        meanings_mapping = get_question_answer_mappings()
        for k_text, answers in meanings_mapping.items():
            k_text = k_text.strip()
            if session.query(Entry).filter(Entry.text == k_text).first():
                continue
            entry = Entry(text=k_text)
            session.add(entry)
            inserted_entry_count += 1
            if len(answers) > 1:
                entries_with_multi_answers.append(k_text)
            for answer_text in answers:
                if not answer_text:
                    entries_with_empty_answers.append(k_text)
                answer = Answer(text=answer_text, entry=entry)
                session.add(answer)
        session.commit()
    print("Inserted entries count:", inserted_entry_count)
    print("entries_with_empty_answers:", len(entries_with_empty_answers))
    print(entries_with_empty_answers)
    print("entries_with_multi_answers:", len(entries_with_multi_answers))
    print(entries_with_multi_answers)


def db_get_all_entries():
    with Session(engine) as session:
        entries = (
            session.query(Entry)
            .filter(Entry.is_hidden == False)
            .order_by(Entry.id.desc())
            .all()
        )
        return entries



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


def db_entry_increment_visit_number(entry_id: int):
    with Session(engine) as session:
        entry = session.query(Entry).filter(Entry.id == entry_id).first()
        if entry:
            entry.visit_count = entry.visit_count + 1
            session.commit()
            return True


def db_get_answer_by_id(answer_id: int):
    with Session(engine) as session:
        return session.query(Answer).filter(Answer.id == answer_id).first()


def db_delete_answer(answer_id: int):
    with Session(engine) as session:
        answer = session.query(Answer).filter(Answer.id == answer_id).first()
        if answer:
            entry_id = answer.question_id
            session.query(Answer).filter(Answer.id == answer_id).delete()
            session.commit()
            return entry_id


def db_update_answer_text(answer_id: int, text: str):
    with Session(engine) as session:
        answer = session.query(Answer).filter(Answer.id == answer_id).first()
        if answer:
            entry_id = answer.question_id
            answer.text = text
            session.commit()
            return entry_id


def db_add_answer(text: str, entry: Entry):
    with Session(engine) as session:
        text = text.strip()
        answer = Answer(text=text, entry=entry)
        session.add(answer)
        session.commit()
        return answer.id


def db_mark_last_review(entry_id: int):
    now = int(time.time())
    with Session(engine) as session:
        entry = session.query(Entry).filter(Entry.id == entry_id).first()
        if entry:
            entry.last_review = now
            state = session.get(GlobalState, 1)
            if state is None:
                state = GlobalState(id=1)
                session.add(state)
            state.last_review_question_id = entry_id
            session.commit()
            return True
    return False


def db_remove_last_review(entry_id: int):
    with Session(engine) as session:
        entry = session.query(Entry).filter(Entry.id == entry_id).first()
        if entry:
            entry.last_review = None
            session.commit()
            return True
    return False


def get_last_reviewed() -> int | None:
    with Session(engine) as session:
        state = session.get(GlobalState, 1)
        return state.last_review_question_id if state else None


def main():
    parser = ArgumentParser(description="Your program's description")

    subparsers = parser.add_subparsers(dest="mode", help="Mode selection")
    subparsers.add_parser("create-table")
    subparsers.add_parser("insert")
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
    if args.mode == "insert":
        insert_entries_and_answers()


if __name__ == "__main__":
    main()
