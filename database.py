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


class Question(Base):
    __tablename__ = "question"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    text: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    answers: Mapped[list["Answer"]] = relationship(
        "Answer",
        back_populates="question",
        lazy="joined",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    example: Mapped[str] = mapped_column(String, nullable=True)
    is_hidden: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    visit_count: Mapped[int] = mapped_column(Integer, nullable=True, default=0)
    last_visit: Mapped[int] = mapped_column(Integer, nullable=True)

    def __str__(self) -> str:
        return (
            f'Question(id={self.id}, text="{self.text}",'
            f" answers={[str(a) for a in self.answers]})"
            f" example: {self.example}"
        )


class Answer(Base):
    __tablename__ = "answer"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    text: Mapped[str] = mapped_column(String, nullable=False)

    # Establish a many-to-one relationship with the Question table
    question_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("question.id", ondelete="CASCADE")
    )
    question: Mapped[Question] = relationship(
        Question, back_populates="answers"
    )

    def __str__(self) -> str:
        return f'Answer(id={self.id}, text="{self.text}"'


# Emit CREATE TABLE DDL
def create_tables():
    Base.metadata.create_all(
        engine,
    )


def insert_questions_and_answers():
    from mappings import get_question_answer_mappings

    inserted_question_count = 0
    questions_with_empty_answers = []
    questions_with_multi_answers = []
    with Session(engine) as session:
        meanings_mapping = get_question_answer_mappings()
        for k_text, answers in meanings_mapping.items():
            k_text = k_text.strip()
            if session.query(Question).filter(Question.text == k_text).first():
                continue
            question = Question(text=k_text)
            session.add(question)
            inserted_question_count += 1
            if len(answers) > 1:
                questions_with_multi_answers.append(k_text)
            for answer_text in answers:
                if not answer_text:
                    questions_with_empty_answers.append(k_text)
                answer = Answer(text=answer_text, question=question)
                session.add(answer)
        session.commit()
    print("Inserted questions count:", inserted_question_count)
    print("questions_with_empty_answers:", len(questions_with_empty_answers))
    print(questions_with_empty_answers)
    print("questions_with_multi_answers:", len(questions_with_multi_answers))
    print(questions_with_multi_answers)


def db_get_all_question():
    with Session(engine) as session:
        questions = session.query(Question).all()
        return questions


def db_get_question_by_id(id: int):
    with Session(engine) as session:
        query = session.query(Question).filter(Question.id == id).first()
        if question := query:
            return question
        else:
            print("No such question")


def db_get_question_by_text(question_text: str):
    with Session(engine) as session:
        query = (
            session.query(Question)
            .filter(Question.text == question_text)
            .first()
        )
        if question := query:
            print(question)
        else:
            print("No such question")


def db_delete_question(id: int):
    with Session(engine) as session:
        session.query(Question).filter(Question.id == id).delete()
        session.commit()


def db_update_question_text(id: int, text: str):
    with Session(engine) as session:
        question = session.query(Question).filter(Question.id == id).first()
        if question:
            question_id = question.id
            question.text = text
            session.commit()
            return question_id


def db_update_example(question_id: int, example_text: str):
    with Session(engine) as session:
        question = (
            session.query(Question).filter(Question.id == question_id).first()
        )
        if question:
            question_id = question.id
            question.example = example_text
            session.commit()
            return question_id


def db_add_question(text: str):
    with Session(engine) as session:
        text = text.strip()
        question = Question(text=text, visit_time=int(time.time()))
        session.add(question)
        session.commit()
        return question.id


def db_question_last_visit_old_enough(id: int):
    with Session(engine) as session:
        question = session.query(Question).filter(Question.id == id).first()
        if question:
            last_visit = question.last_visit
            if not last_visit:
                question.last_visit = int(time.time())
                session.commit()
                return True
            now = int(time.time())
            # last visit more than 12h ago
            if now - last_visit >= 3600 * 12:
                question.last_visit = now
                session.commit()
                return True
            return False


def db_question_increment_visit_number(id: int):
    with Session(engine) as session:
        question = session.query(Question).filter(Question.id == id).first()
        if question:
            old_count = question.visit_count
            question.visit_count = old_count + 1
            session.commit()
            return True


def db_get_answer_by_id(id: int):
    with Session(engine) as session:
        query = session.query(Answer).filter(Answer.id == id).first()
        if answer := query:
            return answer
        else:
            print("No such answer")


def db_delete_answer(id: int):
    with Session(engine) as session:
        answer = session.query(Answer).filter(Answer.id == id).first()
        if answer:
            question_id = answer.question_id
            session.query(Answer).filter(Answer.id == id).delete()
            session.commit()
            return question_id


def db_update_answer_text(id: int, text: str):
    with Session(engine) as session:
        answer = session.query(Answer).filter(Answer.id == id).first()
        if answer:
            question_id = answer.question_id
            answer.text = text
            session.commit()
            return question_id


def db_add_answer(text: str, question: Question):
    with Session(engine) as session:
        text = text.strip()
        answer = Answer(text=text, question=question)
        session.add(answer)
        session.commit()
        return answer.id


def main():
    parser = ArgumentParser(description="Your program's description")

    subparsers = parser.add_subparsers(dest="mode", help="Mode selection")

    create_table_parser = subparsers.add_parser("create-table")

    insert_parser = subparsers.add_parser("insert")

    question_parser = subparsers.add_parser("question")
    question_parser.add_argument(
        "--question", required=True, help="Specify the question"
    )

    args = parser.parse_args()

    print("Mode:", args.mode)
    if args.mode == "question":
        print("Question:", args.question)
        db_get_question_by_text(args.question)
    if args.mode == "create-table":
        create_tables()
    if args.mode == "insert":
        insert_questions_and_answers()


if __name__ == "__main__":
    main()
