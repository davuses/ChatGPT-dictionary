from typing import Optional

import markdown2
from fastapi import Depends, FastAPI, Form, HTTPException, Query, Request
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    RedirectResponse,
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.templating import _TemplateResponse

from database import (
    db_add_answer,
    db_add_question,
    db_delete_answer,
    db_delete_question,
    db_get_all_question,
    db_get_answer_by_id,
    db_get_latest_questions,
    db_get_question_by_id,
    db_mark_last_review,
    db_question_increment_visit_number,
    db_question_last_visit_old_enough,
    db_remove_last_review,
    db_update_answer_text,
    db_update_example,
    db_update_question_text,
    get_last_reviewed,
)
from utils import (
    NOTES_DIR,
    QuestionDisplay,
    build_directory_tree_markdown,
    get_all_words,
    get_how_long_ago,
    get_IPA,
    get_thesaurus_entries,
    highlight_ipa,
    safe_path_note,
)

app = FastAPI()


app.mount("/static", StaticFiles(directory="./static"), name="static")

templates = Jinja2Templates(directory="templates")


class EditAnswerForm(BaseModel):
    answer_text: str

    @classmethod
    def as_form(cls, answer_text: str = Form(...)):
        return cls(answer_text=answer_text)


class EditQuestionForm(BaseModel):
    question_text: str

    @classmethod
    def as_form(cls, question_text: str = Form(...)):
        return cls(question_text=question_text)


class EditExampleForm(BaseModel):
    example_text: Optional[str] = Field(default="", description="Example text")

    @classmethod
    def as_form(cls, example_text: str = Form(None)):
        return cls(example_text=example_text)


class EditNoteForm(BaseModel):
    note_text: Optional[str] = Field(default="", description="Note text")

    @classmethod
    def as_form(cls, note_text: str = Form(None)):
        return cls(note_text=note_text)


class AddQuestionForm(BaseModel):
    question_text: str

    @classmethod
    def as_form(cls, question_text: str = Form(...)):
        return cls(question_text=question_text)


class AddAnswerForm(BaseModel):
    answer_text: str
    question_id: int

    @classmethod
    def as_form(
        cls, answer_text: str = Form(...), question_id: int = Form(...)
    ):
        return cls(answer_text=answer_text, question_id=question_id)


@app.exception_handler(StarletteHTTPException)
async def custom_http_exception_handler(
    request: Request, exc: StarletteHTTPException
):
    if exc.status_code == 404:
        return templates.TemplateResponse(
            "404.html.jinja",
            {"request": request, "detail": exc.detail},
            status_code=404,
        )
    if exc.status_code == 500:
        return templates.TemplateResponse(
            "500.html.jinja",
            {"request": request, "detail": exc.detail},
            status_code=500,
        )
    return HTMLResponse(content=str(exc.detail), status_code=exc.status_code)


@app.get("/static/{file_name}", include_in_schema=False)
async def static_file(file_name):
    return FileResponse(f"./static/{file_name}")


@app.get("/", response_class=HTMLResponse)
async def root_page(
    request: Request,
    show_example: bool = Query(False),
    questions_only: bool = Query(False),
    review_mode: bool = Query(False),
):
    is_all_questions = True
    if is_all_questions:
        questions = db_get_all_question()
    else:
        question_count = 1000
        questions = db_get_latest_questions(question_count)
    questions_count = len(questions)
    q_list: list[QuestionDisplay] = []
    # (question.id, q_text, q_context, example)
    for question in questions:
        question_text = question.text
        if "When i ask you a word" in question_text:
            continue
        q_context = ""
        q_text = question_text
        if " - " in question_text:
            q_text = question_text.split(" - ")[-1].strip()
            q_context = question_text.split(" - ")[0]

        q_list.append(
            QuestionDisplay(
                question=question,
                q_text=q_text,
                q_context=q_context,
                last_review_elapse=get_how_long_ago(question.last_review),
            )
        )

    context = {
        "questions_count": questions_count,
        "q_list": q_list,
        "questions_only": questions_only,
        "show_example": show_example,
        "review_mode": review_mode,
        "is_all_questions": is_all_questions,
        "last_review_question_id": get_last_reviewed(),
    }
    return templates.TemplateResponse(
        request=request, name="root.html.jinja", context=context
    )


@app.get("/question/{question_id}", response_class=HTMLResponse)
async def question_page(question_id: int, request: Request):
    question = db_get_question_by_id(question_id)
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")
    visit_count = question.visit_count
    if db_question_last_visit_old_enough(question.id):
        db_question_increment_visit_number(question.id)
        # a bit of hack
        visit_count += 1
    # Only display the first answer
    answer_exist = True if question.answers else False
    answer_html = None
    answer_id = None
    if answer_exist:
        a = question.answers[0]
        answer_html = markdown2.markdown(a.text, extras=["strike"])
        answer_id = a.id
    word = question.text.split(" - ")[-1].strip()
    IPA_transcript = get_IPA(word)
    example_html = (
        markdown2.markdown(question.example, extras=["strike", "tables"])
        if question.example
        else ""
    )
    example_html = highlight_ipa(example_html)
    context = {
        "visit_count": visit_count,
        "last_visit_elapsed": get_how_long_ago(question.last_visit),
        "last_review_elapsed": get_how_long_ago(question.last_review),
        "question_text": question.text,
        "question_id": question_id,
        "IPA_transcript": IPA_transcript,
        "word": word,
        "answer_exist": answer_exist,
        "answer_html": answer_html,
        "answer_id": answer_id,
        "example_html": example_html,
    }
    return templates.TemplateResponse(
        request=request, name="question.html.jinja", context=context
    )


@app.get("/edit_question/{question_id}", response_class=HTMLResponse)
async def edit_question_page(question_id: int, request: Request):
    question = db_get_question_by_id(question_id)
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")

    context = {"question_id": question_id, "question_text": question.text}
    return templates.TemplateResponse(
        request=request, name="edit_question.html.jinja", context=context
    )


@app.get("/edit_answer/{answer_id}", response_class=HTMLResponse)
async def edit_answer_page(answer_id: int, request: Request):
    answer = db_get_answer_by_id(answer_id)
    if not answer:
        raise HTTPException(status_code=404, detail="Answer not found")
    context = {"answer_text": answer.text, "answer_id": answer_id}
    return templates.TemplateResponse(
        request=request, name="edit_answer.html.jinja", context=context
    )


@app.get("/edit_example/{question_id}", response_class=HTMLResponse)
async def edit_example_page(question_id: int, request: Request):
    question = db_get_question_by_id(question_id)
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")

    context = {
        "question_id": question_id,
        "question_example": question.example or "",
    }
    return templates.TemplateResponse(
        request=request, name="edit_example.html.jinja", context=context
    )


@app.get("/add_question", response_class=HTMLResponse)
async def add_question_page(request: Request):
    return templates.TemplateResponse(
        request=request, name="add_question.html.jinja"
    )


@app.get("/add_answer", response_class=HTMLResponse)
async def add_answer_page(qid: int, request: Request):
    context = {"qid": qid}
    return templates.TemplateResponse(
        request=request, name="add_answer.html.jinja", context=context
    )


@app.post("/edit_question/{question_id}", response_class=HTMLResponse)
async def edit_question(
    question_id: int,
    form_data: EditQuestionForm = Depends(EditQuestionForm.as_form),
):
    updated_text = form_data.question_text.strip()
    if not updated_text:
        return "Question text cannot be empty"
    try:
        if q_id := db_update_question_text(question_id, updated_text):
            return RedirectResponse(url=f"/question/{q_id}", status_code=303)
    except IntegrityError:
        return "Question text UNIQUE constraint failed"


@app.post("/edit_answer/{answer_id}", response_class=HTMLResponse)
async def edit_answer(
    answer_id: int, form_data: EditAnswerForm = Depends(EditAnswerForm.as_form)
):
    updated_text = form_data.answer_text
    if question_id := db_update_answer_text(answer_id, updated_text):
        return RedirectResponse(url=f"/question/{question_id}", status_code=303)


@app.post("/edit_example/{question_id}", response_class=HTMLResponse)
async def edit_example(
    question_id: int,
    form_data: EditExampleForm = Depends(EditExampleForm.as_form),
):
    if not (updated_text := form_data.example_text):
        updated_text = ""
    if returned_qid := db_update_example(question_id, updated_text):
        return RedirectResponse(
            url=f"/question/{returned_qid}", status_code=303
        )


@app.get("/delete_question/{question_id}", response_class=HTMLResponse)
async def delete_question(question_id: int):
    db_delete_question(question_id)
    return "200"


@app.get("/delete_answer/{answer_id}", response_class=HTMLResponse)
async def delete_answer(answer_id: int):
    if question_id := db_delete_answer(answer_id):
        return RedirectResponse(url=f"/question/{question_id}", status_code=303)


@app.post("/add_question", response_class=HTMLResponse)
async def add_question(
    form_data: AddQuestionForm = Depends(AddQuestionForm.as_form),
):
    updated_text = form_data.question_text.strip()
    if not updated_text:
        return "Question text cannot be empty"
    try:
        if q_id := db_add_question(updated_text):
            return RedirectResponse(url=f"/question/{q_id}", status_code=303)
    except IntegrityError:
        return "Question text UNIQUE constraint failed"


@app.post("/add_answer", response_class=HTMLResponse)
async def add_answer(
    form_data: AddAnswerForm = Depends(AddAnswerForm.as_form),
):
    updated_text = form_data.answer_text
    qid = form_data.question_id
    if question := db_get_question_by_id(qid):
        db_add_answer(updated_text, question=question)
        return RedirectResponse(url=f"/question/{qid}", status_code=303)
    return "Question doesn't exist"


@app.post("/question/{question_id}/mark_last_review")
async def mark_last_review(question_id: int):
    success = db_mark_last_review(question_id)
    if not success:
        raise HTTPException(status_code=404, detail="Question not found")
    return {"message": "Last review marked"}


@app.post("/question/{question_id}/remove_last_review")
async def remove_last_review(question_id: int):
    success = db_remove_last_review(question_id)
    if not success:
        raise HTTPException(status_code=404, detail="Question not found")
    return {"message": "Last review removed"}


@app.get("/show_synonyms/{qid}", response_class=HTMLResponse)
def show_synonyms(qid: int, request: Request):
    question = db_get_question_by_id(qid)
    if not question:
        return "No question"
    question_text: str = question.text
    try:
        word = question_text.split(" - ")[-1]
        assert " " not in word
    except (IndexError, AssertionError):
        raise HTTPException(status_code=404, detail="Word not valid")
    try:
        entries = get_thesaurus_entries(word)
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error fetching thesaurus entries: {e}"
        )
    context = {
        "qid": qid,
        "word": word or "",
        "entries": entries,
        "all_words": get_all_words(),  # pass this in
    }
    return templates.TemplateResponse(
        request=request, name="synonyms.html.jinja", context=context
    )


@app.get("/notes/", response_class=HTMLResponse)
async def notes(request: Request):
    toc_html = ""
    text = build_directory_tree_markdown(NOTES_DIR)
    note_html = markdown2.markdown(
        text,
        extras=["strike", "tables", "toc", "fenced-code-blocks"],
    )
    toc_html = getattr(note_html, "toc_html", "")
    title = "Notes Tree"
    toc_exist = bool(toc_html)
    context = {
        "title": title,
        "toc_html": toc_html,
        "note_html": note_html,
        "is_dir": True,
        "toc_exist": toc_exist,
    }
    return templates.TemplateResponse(
        request=request, name="notes.html.jinja", context=context
    )


@app.get("/view_note/{note_path:path}", response_class=HTMLResponse)
def view_note(note_path: str, request: Request) -> _TemplateResponse:
    """Return the rendered HTML of a markdown note by relative path."""
    full_path = safe_path_note(note_path)
    content = full_path.read_text(encoding="utf-8")
    note_html = markdown2.markdown(
        content,
        extras=["strike", "tables", "toc", "fenced-code-blocks"],
    )
    toc_html = getattr(note_html, "toc_html", "")
    title = full_path.name
    toc_exist = bool(toc_html)
    context = {
        "title": title,
        "toc_html": toc_html,
        "note_html": note_html,
        "is_dir": False,
        "toc_exist": toc_exist,
    }
    return templates.TemplateResponse(
        request=request, name="notes.html.jinja", context=context
    )


@app.get("/edit_note/{note_path:path}", response_class=HTMLResponse)
async def edit_note_page(note_path: str, request: Request):
    full_path = safe_path_note(note_path)
    content = full_path.read_text(encoding="utf-8")
    context = {"note_text": content, "note_path": note_path}
    return templates.TemplateResponse(
        request=request, name="edit_note.html.jinja", context=context
    )


@app.post("/edit_note/{note_path:path}", response_class=HTMLResponse)
async def edit_note(
    note_path: str,
    request: Request,
    form_data: EditNoteForm = Depends(EditNoteForm.as_form),
):
    full_path = safe_path_note(note_path)
    updated_text = form_data.note_text or ""
    try:
        full_path.write_text(updated_text, encoding="utf-8")
        return RedirectResponse(
            url=request.url_for("view_note", note_path=note_path),
            status_code=303,
        )
    except (OSError, IOError):
        return templates.TemplateResponse(
            request=request,
            name="404.html.jinja",
            context={"message": "Unable to edit the file"},
        )
