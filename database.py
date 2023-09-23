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

from mappings import meanings_mapping

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
    question_id = mapped_column(Integer, ForeignKey("question.id"))
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
        for k in meanings_mapping:
            question = Question(text=k)
            if session.query(Question).filter(Question.text == k).first():
                continue
            session.add(question)
            answers = meanings_mapping[k]
            for answer_text in answers:
                answer = Answer(text=answer_text, question=question)
                session.add(answer)
        session.commit()


def get_all_question():
    with Session(engine) as session:
        questions = session.query(Question).all()
        return questions


def get_question_by_id(id: int):
    with Session(engine) as session:
        query = session.query(Question).filter(Question.id == id).first()
        if question := query:
            return question
        else:
            print("No such question")


def delete_question(id: int):
    with Session(engine) as session:
        # session.query(Question).filter(Question.id == id).delete()
        question = session.query(Question).filter(Question.id == id).first()
        if question:
            question.is_hidden = True
            session.commit()


def get_question_by_text(question_text: str):
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


if __name__ == "__main__":
    # create_tables()
    insert_questions_and_answers()
    # get_question_by_text("meek")
