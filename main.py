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
    db_add_entry,
    db_delete_answer,
    db_delete_entry,
    db_entry_increment_visit_number,
    db_entry_last_visit_old_enough,
    db_get_all_entries,
    db_get_answer_by_id,
    db_get_entry_by_id,
    db_mark_last_review,
    db_remove_last_review,
    db_update_answer_text,
    db_update_entry_text,
    db_update_example,
    get_last_reviewed,
)
from utils import (
    NOTES_DIR,
    EntryDisplay,
    build_directory_tree_markdown,
    get_all_words,
    get_how_long_ago,
    get_IPA,
    get_thesaurus_entries,
    highlight_ipa,
    invalidate_words_cache,
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


class EditEntryForm(BaseModel):
    entry_text: str

    @classmethod
    def as_form(cls, entry_text: str = Form(...)):
        return cls(entry_text=entry_text)


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


class AddEntryForm(BaseModel):
    entry_text: str

    @classmethod
    def as_form(cls, entry_text: str = Form(...)):
        return cls(entry_text=entry_text)


class AddAnswerForm(BaseModel):
    answer_text: str
    entry_id: int

    @classmethod
    def as_form(cls, answer_text: str = Form(...), entry_id: int = Form(...)):
        return cls(answer_text=answer_text, entry_id=entry_id)


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
    entries_only: bool = Query(False),
    review_mode: bool = Query(False),
):
    entries = db_get_all_entries()
    entries_count = len(entries)
    q_list: list[EntryDisplay] = []
    for entry in entries:
        entry_text = entry.text
        q_context = ""
        q_text = entry_text
        if " - " in entry_text:
            q_text = entry_text.split(" - ")[-1].strip()
            q_context = entry_text.split(" - ")[0]

        q_list.append(
            EntryDisplay(
                entry=entry,
                q_text=q_text,
                q_context=q_context,
                last_review_elapse=get_how_long_ago(entry.last_review),
            )
        )

    context = {
        "entries_count": entries_count,
        "q_list": q_list,
        "entries_only": entries_only,
        "show_example": show_example,
        "review_mode": review_mode,
        "last_review_entry_id": get_last_reviewed(),
    }
    return templates.TemplateResponse(
        request=request, name="root.html.jinja", context=context
    )


@app.get("/entry/{entry_id}", response_class=HTMLResponse)
async def entry_page(entry_id: int, request: Request):
    entry = db_get_entry_by_id(entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    visit_count = entry.visit_count
    if db_entry_last_visit_old_enough(entry.id):
        db_entry_increment_visit_number(entry.id)
        # a bit of hack
        visit_count += 1
    # Only display the first answer
    answer_exist = bool(entry.answers)
    answer_html = None
    answer_id = None
    if answer_exist:
        a = entry.answers[0]
        answer_html = markdown2.markdown(a.text, extras=["strike"])
        answer_id = a.id
    word = entry.text.split(" - ")[-1].strip()
    IPA_transcript = get_IPA(word)
    example_html = (
        markdown2.markdown(entry.example, extras=["strike", "tables"])
        if entry.example
        else ""
    )
    example_html = highlight_ipa(example_html)
    context = {
        "visit_count": visit_count,
        "last_visit_elapsed": get_how_long_ago(entry.last_visit),
        "last_review_elapsed": get_how_long_ago(entry.last_review),
        "entry_text": entry.text,
        "entry_id": entry_id,
        "IPA_transcript": IPA_transcript,
        "word": word,
        "answer_exist": answer_exist,
        "answer_html": answer_html,
        "answer_id": answer_id,
        "example_html": example_html,
    }
    return templates.TemplateResponse(
        request=request, name="entry.html.jinja", context=context
    )


@app.get("/edit_entry/{entry_id}", response_class=HTMLResponse)
async def edit_entry_page(entry_id: int, request: Request):
    entry = db_get_entry_by_id(entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")

    context = {"entry_id": entry_id, "entry_text": entry.text}
    return templates.TemplateResponse(
        request=request, name="edit_entry.html.jinja", context=context
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


@app.get("/edit_example/{entry_id}", response_class=HTMLResponse)
async def edit_example_page(entry_id: int, request: Request):
    entry = db_get_entry_by_id(entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")

    context = {
        "entry_id": entry_id,
        "entry_example": entry.example or "",
    }
    return templates.TemplateResponse(
        request=request, name="edit_example.html.jinja", context=context
    )


@app.get("/add_entry", response_class=HTMLResponse)
async def add_entry_page(request: Request):
    return templates.TemplateResponse(
        request=request, name="add_entry.html.jinja"
    )


@app.get("/add_answer", response_class=HTMLResponse)
async def add_answer_page(entry_id: int, request: Request):
    context = {"entry_id": entry_id}
    return templates.TemplateResponse(
        request=request, name="add_answer.html.jinja", context=context
    )


@app.post("/edit_entry/{entry_id}", response_class=HTMLResponse)
async def edit_entry(
    entry_id: int,
    form_data: EditEntryForm = Depends(EditEntryForm.as_form),
):
    updated_text = form_data.entry_text.strip()
    if not updated_text:
        raise HTTPException(status_code=400, detail="Entry text cannot be empty")
    try:
        if e_id := db_update_entry_text(entry_id, updated_text):
            invalidate_words_cache()
            return RedirectResponse(url=f"/entry/{e_id}", status_code=303)
    except IntegrityError:
        raise HTTPException(status_code=409, detail="An entry with that text already exists")


@app.post("/edit_answer/{answer_id}", response_class=HTMLResponse)
async def edit_answer(
    answer_id: int, form_data: EditAnswerForm = Depends(EditAnswerForm.as_form)
):
    updated_text = form_data.answer_text
    if entry_id := db_update_answer_text(answer_id, updated_text):
        return RedirectResponse(url=f"/entry/{entry_id}", status_code=303)


@app.post("/edit_example/{entry_id}", response_class=HTMLResponse)
async def edit_example(
    entry_id: int,
    form_data: EditExampleForm = Depends(EditExampleForm.as_form),
):
    if not (updated_text := form_data.example_text):
        updated_text = ""
    if updated_eid := db_update_example(entry_id, updated_text):
        return RedirectResponse(url=f"/entry/{updated_eid}", status_code=303)


@app.delete("/delete_entry/{entry_id}")
async def delete_entry(entry_id: int):
    db_delete_entry(entry_id)
    invalidate_words_cache()
    return {"message": "deleted"}


@app.delete("/delete_answer/{answer_id}", response_class=HTMLResponse)
async def delete_answer(answer_id: int):
    if entry_id := db_delete_answer(answer_id):
        return RedirectResponse(url=f"/entry/{entry_id}", status_code=303)


@app.post("/add_entry", response_class=HTMLResponse)
async def add_entry(
    form_data: AddEntryForm = Depends(AddEntryForm.as_form),
):
    updated_text = form_data.entry_text.strip()
    if not updated_text:
        raise HTTPException(status_code=400, detail="Entry text cannot be empty")
    try:
        if e_id := db_add_entry(updated_text):
            invalidate_words_cache()
            return RedirectResponse(url=f"/entry/{e_id}", status_code=303)
    except IntegrityError:
        raise HTTPException(status_code=409, detail="An entry with that text already exists")


@app.post("/add_answer", response_class=HTMLResponse)
async def add_answer(
    form_data: AddAnswerForm = Depends(AddAnswerForm.as_form),
):
    updated_text = form_data.answer_text
    entry_id = form_data.entry_id
    if entry := db_get_entry_by_id(entry_id):
        db_add_answer(updated_text, entry=entry)
        return RedirectResponse(url=f"/entry/{entry_id}", status_code=303)
    raise HTTPException(status_code=404, detail="Entry not found")


@app.post("/entry/{entry_id}/mark_last_review")
async def mark_last_review(entry_id: int):
    success = db_mark_last_review(entry_id)
    if not success:
        raise HTTPException(status_code=404, detail="Entry not found")
    return {"message": "Last review marked"}


@app.post("/entry/{entry_id}/remove_last_review")
async def remove_last_review(entry_id: int):
    success = db_remove_last_review(entry_id)
    if not success:
        raise HTTPException(status_code=404, detail="Entry not found")
    return {"message": "Last review removed"}


@app.get("/show_synonyms/{entry_id}", response_class=HTMLResponse)
def show_synonyms(entry_id: int, request: Request):
    entry = db_get_entry_by_id(entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    entry_text: str = entry.text
    word = entry_text.split(" - ")[-1]
    if " " in word:
        raise HTTPException(status_code=404, detail="Word not valid")
    try:
        entries = get_thesaurus_entries(word)
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error fetching thesaurus entries: {e}"
        )
    context = {
        "entry_id": entry_id,
        "word": word or "",
        "entries": entries,
        "all_words": get_all_words(),
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
    title = "IELTS Notes"
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
