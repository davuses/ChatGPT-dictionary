from argparse import ArgumentParser

from sqlalchemy import (
    Boolean,
    ForeignKey,
    Integer,
    String,
    create_engine,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    mapped_column,
    relationship,
)

from mappings import get_question_answer_mappings

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
        "Answer", back_populates="question", lazy="joined"
    )
    is_hidden: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )

    def __str__(self) -> str:
        return (
            f'Question(id={self.id}, text="{self.text}",'
            f" answers={[str(a) for a in self.answers]})"
        )


class Answer(Base):
    __tablename__ = "answer"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    text: Mapped[str] = mapped_column(String, nullable=False)

    # Establish a many-to-one relationship with the Question table
    question_id: Mapped[int] = mapped_column(Integer, ForeignKey("question.id"))
    question: Mapped[Question] = relationship(
        Question, back_populates="answers"
    )

    def __str__(self) -> str:
        return f'Answers(id={self.id}, text="{self.text}"'


# Emit CREATE TABLE DDL
def create_tables():
    Base.metadata.create_all(
        engine,
    )


def insert_questions_and_answers():
    with Session(engine) as session:
        meanings_mapping = get_question_answer_mappings()
        for k, answers in meanings_mapping.items():
            question = Question(text=k)
            if session.query(Question).filter(Question.text == k).first():
                continue
            session.add(question)
            # answers = meanings_mapping[k]
            for answer_text in answers:
                answer = Answer(text=answer_text, question=question)
                session.add(answer)
        session.commit()


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


def db_update_answer_text(id: int, markdown_text: str):
    with Session(engine) as session:
        answer = session.query(Answer).filter(Answer.id == id).first()
        if answer:
            question_id = answer.question_id
            answer.text = markdown_text
            session.commit()
            return question_id


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
