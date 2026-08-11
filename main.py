import time
from dataclasses import replace
from typing import Optional

import markdown2
from fastapi import Depends, FastAPI, Form, HTTPException, Query, Request
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.templating import _TemplateResponse

from database import (
    ENTRIES_PAGE_SIZE,
    db_add_definition,
    db_add_entry,
    db_count_entries,
    db_count_entries_visited_since,
    db_delete_definition,
    db_delete_entry,
    db_entry_increment_visit_count,
    db_entry_last_visit_old_enough,
    db_get_definition_by_id,
    db_get_entries_page,
    db_get_entry_by_id,
    db_get_entry_page_number,
    db_clear_review_bookmark,
    db_set_review_bookmark,
    db_update_definition_text,
    db_update_entry_text,
    db_update_example,
    get_review_bookmark,
)
from utils import (
    NOTES_DIR,
    EntryDisplay,
    build_directory_tree_markdown,
    get_all_words,
    get_how_long_ago,
    get_IPA,
    get_thesaurus_senses,
    highlight_ipa,
    invalidate_quiz_pool_cache,
    invalidate_words_cache,
    normalize_pronoun_casing,
    pick_daily_question,
    pick_random_question,
    safe_path_note,
)

app = FastAPI()


app.mount("/static", StaticFiles(directory="./static"), name="static")

templates = Jinja2Templates(directory="templates")


class EditDefinitionForm(BaseModel):
    definition_text: str

    @classmethod
    def as_form(cls, definition_text: str = Form(...)):
        return cls(definition_text=definition_text)


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


class AddDefinitionForm(BaseModel):
    definition_text: str
    entry_id: int

    @classmethod
    def as_form(
        cls, definition_text: str = Form(...), entry_id: int = Form(...)
    ):
        return cls(definition_text=definition_text, entry_id=entry_id)


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
async def root_page(request: Request):
    review_bookmark_entry_id = get_review_bookmark()
    seven_days_ago = int(time.time()) - 7 * 86400
    daily_question = pick_daily_question()
    if daily_question and db_entry_last_visit_old_enough(daily_question.entry_id):
        db_entry_increment_visit_count(daily_question.entry_id)
    context = {
        "entries_count": db_count_entries(),
        "visited_last_7_days": db_count_entries_visited_since(seven_days_ago),
        "review_bookmark_entry_id": review_bookmark_entry_id,
        "question": daily_question,
    }
    return templates.TemplateResponse(
        request=request, name="root.html.jinja", context=context
    )


QUIZ_EXCLUDE_HISTORY_SIZE = 15


@app.get("/quiz", response_class=HTMLResponse)
async def quiz_page(request: Request, exclude: str = Query("")):
    # Order matters here (oldest-first) so the trailing slice below keeps the
    # *most recently seen* entries, not an arbitrary subset.
    exclude_ids_ordered = [int(x) for x in exclude.split(",") if x.strip().isdigit()]
    exclude_ids_ordered = list(dict.fromkeys(exclude_ids_ordered))

    question = pick_random_question(exclude_entry_ids=set(exclude_ids_ordered))
    if question and db_entry_last_visit_old_enough(question.entry_id):
        db_entry_increment_visit_count(question.entry_id)

    next_exclude_ids = exclude_ids_ordered + ([question.entry_id] if question else [])
    next_exclude_ids = list(dict.fromkeys(next_exclude_ids))
    next_exclude = ",".join(
        str(i) for i in next_exclude_ids[-QUIZ_EXCLUDE_HISTORY_SIZE:]
    )

    context = {"question": question, "next_exclude": next_exclude}
    return templates.TemplateResponse(
        request=request, name="quiz.html.jinja", context=context
    )


@app.get("/entries", response_class=HTMLResponse)
async def entries_page(
    request: Request,
    show_example: bool = Query(False),
    entries_only: bool = Query(False),
    q: str = Query(""),
    page: int = Query(1, ge=1),
):
    entries, total_count = db_get_entries_page(
        query=q, include_examples=show_example, page=page
    )
    review_bookmark_entry_id = get_review_bookmark()
    entry_displays: list[EntryDisplay] = []
    for entry in entries:
        entry_text = entry.text
        context_text = ""
        display_text = entry_text
        if " - " in entry_text:
            display_text = entry_text.split(" - ")[-1].strip()
            context_text = entry_text.split(" - ")[0]
        context_text = normalize_pronoun_casing(context_text)

        if show_example and entry.example:
            entry = replace(entry, example=normalize_pronoun_casing(entry.example))

        entry_displays.append(
            EntryDisplay(
                entry=entry,
                text=display_text,
                context=context_text,
            )
        )

    total_pages = max(1, -(-total_count // ENTRIES_PAGE_SIZE))  # ceil div
    context = {
        "entries_count": total_count,
        "entry_displays": entry_displays,
        "entries_only": entries_only,
        "show_example": show_example,
        "review_bookmark_entry_id": review_bookmark_entry_id,
        "search_query": q,
        "page": page,
        "total_pages": total_pages,
        "has_prev_page": page > 1,
        "has_next_page": page < total_pages,
    }
    return templates.TemplateResponse(
        request=request, name="entries.html.jinja", context=context
    )


@app.get("/entry/{entry_id}", response_class=HTMLResponse)
async def entry_page(entry_id: int, request: Request):
    entry = db_get_entry_by_id(entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    visit_count = entry.visit_count
    if db_entry_last_visit_old_enough(entry.id):
        db_entry_increment_visit_count(entry.id)
        # a bit of hack
        visit_count += 1
    # Only display the first definition
    definition_exists = bool(entry.definitions)
    definition_html = None
    definition_id = None
    if definition_exists:
        d = entry.definitions[0]
        definition_html = markdown2.markdown(d.text, extras=["strike"])
        definition_id = d.id
    word = entry.text.split(" - ")[-1].strip()
    IPA_transcript = get_IPA(word)
    example_html = (
        markdown2.markdown(
            normalize_pronoun_casing(entry.example), extras=["strike", "tables"]
        )
        if entry.example
        else ""
    )
    example_html = highlight_ipa(example_html)
    review_bookmark_entry_id = get_review_bookmark()
    context = {
        "visit_count": visit_count,
        "last_visit_elapsed": get_how_long_ago(entry.last_visit),
        "is_review_bookmark": entry_id == review_bookmark_entry_id,
        "entry_text": normalize_pronoun_casing(entry.text),
        "entry_id": entry_id,
        "IPA_transcript": IPA_transcript,
        "word": word,
        "definition_exists": definition_exists,
        "definition_html": definition_html,
        "definition_id": definition_id,
        "example_html": example_html,
        "needs_markdown_css": True,
    }
    return templates.TemplateResponse(
        request=request, name="entry.html.jinja", context=context
    )


@app.get("/edit_entry/{entry_id}", response_class=HTMLResponse)
async def edit_entry_page(entry_id: int, request: Request):
    entry = db_get_entry_by_id(entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")

    context = {"entry_id": entry_id, "entry_text": entry.text, "needs_editor": True}
    return templates.TemplateResponse(
        request=request, name="edit_entry.html.jinja", context=context
    )


@app.get("/edit_definition/{definition_id}", response_class=HTMLResponse)
async def edit_definition_page(definition_id: int, request: Request):
    definition = db_get_definition_by_id(definition_id)
    if not definition:
        raise HTTPException(status_code=404, detail="Definition not found")
    context = {
        "definition_text": definition.text,
        "definition_id": definition_id,
        "needs_editor": True,
    }
    return templates.TemplateResponse(
        request=request, name="edit_definition.html.jinja", context=context
    )


@app.get("/edit_example/{entry_id}", response_class=HTMLResponse)
async def edit_example_page(entry_id: int, request: Request):
    entry = db_get_entry_by_id(entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")

    context = {
        "entry_id": entry_id,
        "entry_example": entry.example or "",
        "needs_editor": True,
    }
    return templates.TemplateResponse(
        request=request, name="edit_example.html.jinja", context=context
    )


@app.get("/add_entry", response_class=HTMLResponse)
async def add_entry_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="add_entry.html.jinja",
        context={"needs_editor": True},
    )


@app.get("/add_definition", response_class=HTMLResponse)
async def add_definition_page(entry_id: int, request: Request):
    context = {"entry_id": entry_id, "needs_editor": True}
    return templates.TemplateResponse(
        request=request, name="add_definition.html.jinja", context=context
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
            invalidate_quiz_pool_cache()
            return RedirectResponse(url=f"/entry/{e_id}", status_code=303)
    except IntegrityError:
        raise HTTPException(status_code=409, detail="An entry with that text already exists")


@app.post("/edit_definition/{definition_id}", response_class=HTMLResponse)
async def edit_definition(
    definition_id: int,
    form_data: EditDefinitionForm = Depends(EditDefinitionForm.as_form),
):
    updated_text = form_data.definition_text
    if entry_id := db_update_definition_text(definition_id, updated_text):
        return RedirectResponse(url=f"/entry/{entry_id}", status_code=303)


@app.post("/edit_example/{entry_id}", response_class=HTMLResponse)
async def edit_example(
    entry_id: int,
    form_data: EditExampleForm = Depends(EditExampleForm.as_form),
):
    if not (updated_text := form_data.example_text):
        updated_text = ""
    if updated_eid := db_update_example(entry_id, updated_text):
        invalidate_quiz_pool_cache()
        return RedirectResponse(url=f"/entry/{updated_eid}", status_code=303)


@app.delete("/delete_entry/{entry_id}")
async def delete_entry(entry_id: int):
    db_delete_entry(entry_id)
    invalidate_words_cache()
    invalidate_quiz_pool_cache()
    return {"message": "deleted"}


@app.delete("/delete_definition/{definition_id}", response_class=HTMLResponse)
async def delete_definition(definition_id: int):
    if entry_id := db_delete_definition(definition_id):
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
            invalidate_quiz_pool_cache()
            return RedirectResponse(url=f"/entry/{e_id}", status_code=303)
    except IntegrityError:
        raise HTTPException(status_code=409, detail="An entry with that text already exists")


@app.post("/add_definition", response_class=HTMLResponse)
async def add_definition(
    form_data: AddDefinitionForm = Depends(AddDefinitionForm.as_form),
):
    updated_text = form_data.definition_text
    entry_id = form_data.entry_id
    if entry := db_get_entry_by_id(entry_id):
        db_add_definition(updated_text, entry=entry)
        return RedirectResponse(url=f"/entry/{entry_id}", status_code=303)
    raise HTTPException(status_code=404, detail="Entry not found")


@app.post("/entry/{entry_id}/set_review_bookmark")
async def set_review_bookmark(entry_id: int):
    success = db_set_review_bookmark(entry_id)
    if not success:
        raise HTTPException(status_code=404, detail="Entry not found")
    return {"message": "Review bookmark set"}


@app.post("/entry/{entry_id}/clear_review_bookmark")
async def clear_review_bookmark(entry_id: int):
    success = db_clear_review_bookmark(entry_id)
    if not success:
        raise HTTPException(status_code=404, detail="Entry not found")
    return {"message": "Review bookmark cleared"}


@app.get("/review_bookmark")
async def review_bookmark():
    return JSONResponse(
        {"entry_id": get_review_bookmark()},
        headers={"Cache-Control": "no-store"},
    )


@app.get("/resume_review")
async def resume_review():
    entry_id = get_review_bookmark()
    if not entry_id:
        return RedirectResponse(url="/entries", status_code=303)
    page = db_get_entry_page_number(entry_id) or 1
    return RedirectResponse(
        url=f"/entries?page={page}#{entry_id}", status_code=303
    )


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
        senses = get_thesaurus_senses(word)
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error fetching thesaurus senses: {e}"
        )
    context = {
        "entry_id": entry_id,
        "word": word or "",
        "senses": senses,
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
        "needs_markdown_css": True,
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
        "needs_markdown_css": True,
    }
    return templates.TemplateResponse(
        request=request, name="notes.html.jinja", context=context
    )


@app.get("/edit_note/{note_path:path}", response_class=HTMLResponse)
async def edit_note_page(note_path: str, request: Request):
    full_path = safe_path_note(note_path)
    content = full_path.read_text(encoding="utf-8")
    context = {
        "note_text": content,
        "note_path": note_path,
        "needs_editor": True,
    }
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
