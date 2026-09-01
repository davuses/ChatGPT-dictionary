import time
import urllib.parse
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
from starlette.middleware.sessions import SessionMiddleware
from starlette.templating import _TemplateResponse

from auth import (
    SESSION_MAX_AGE,
    auth_template_context,
    authenticate,
    end_admin_session,
    get_auth_settings,
    get_csrf_token,
    is_admin,
    require_admin,
    require_admin_with_form_csrf,
    require_admin_with_header_csrf,
    safe_next_path,
    start_admin_session,
    verify_csrf_value,
)

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
    highlight_matches,
    invalidate_quiz_pool_cache,
    invalidate_words_cache,
    normalize_pronoun_casing,
    pick_random_question,
    QuizQuestion,
    safe_path_note,
)

auth_settings = get_auth_settings()

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(
    SessionMiddleware,
    secret_key=auth_settings.session_secret,
    session_cookie="dictionary_session",
    max_age=SESSION_MAX_AGE,
    same_site="lax",
    https_only=auth_settings.https_only,
)


app.mount("/static", StaticFiles(directory="./static"), name="static")

templates = Jinja2Templates(
    directory="templates", context_processors=[auth_template_context]
)


class CsrfForm(BaseModel):
    csrf_token: str


class EditDefinitionForm(CsrfForm):
    definition_text: str

    @classmethod
    async def as_form(
        cls, definition_text: str = Form(...), csrf_token: str = Form(...)
    ):
        return cls(definition_text=definition_text, csrf_token=csrf_token)


class EditEntryForm(CsrfForm):
    entry_text: str

    @classmethod
    async def as_form(cls, entry_text: str = Form(...), csrf_token: str = Form(...)):
        return cls(entry_text=entry_text, csrf_token=csrf_token)


class EditExampleForm(CsrfForm):
    example_text: Optional[str] = Field(default="", description="Example text")

    @classmethod
    async def as_form(
        cls, example_text: str = Form(None), csrf_token: str = Form(...)
    ):
        return cls(example_text=example_text, csrf_token=csrf_token)


class EditNoteForm(CsrfForm):
    note_text: Optional[str] = Field(default="", description="Note text")

    @classmethod
    async def as_form(cls, note_text: str = Form(None), csrf_token: str = Form(...)):
        return cls(note_text=note_text, csrf_token=csrf_token)


class AddEntryForm(CsrfForm):
    entry_text: str

    @classmethod
    async def as_form(cls, entry_text: str = Form(...), csrf_token: str = Form(...)):
        return cls(entry_text=entry_text, csrf_token=csrf_token)


class AddDefinitionForm(CsrfForm):
    definition_text: str
    entry_id: int

    @classmethod
    async def as_form(
        cls,
        definition_text: str = Form(...),
        entry_id: int = Form(...),
        csrf_token: str = Form(...),
    ):
        return cls(
            definition_text=definition_text,
            entry_id=entry_id,
            csrf_token=csrf_token,
        )


class LoginForm(CsrfForm):
    username: str
    password: str
    next_path: str = "/"

    @classmethod
    async def as_form(
        cls,
        username: str = Form(...),
        password: str = Form(...),
        next_path: str = Form("/"),
        csrf_token: str = Form(...),
    ):
        return cls(
            username=username,
            password=password,
            next_path=next_path,
            csrf_token=csrf_token,
        )


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, next_path: str = Query("/", alias="next")):
    destination = safe_next_path(next_path)
    if is_admin(request):
        return RedirectResponse(url=destination, status_code=303)
    context = {
        "next_path": destination,
        "login_csrf_token": get_csrf_token(request),
        "error": None,
    }
    return templates.TemplateResponse(
        request=request, name="login.html.jinja", context=context
    )


@app.post("/login", response_class=HTMLResponse)
async def login(
    request: Request,
    form_data: LoginForm = Depends(LoginForm.as_form),
):
    verify_csrf_value(request, form_data.csrf_token)
    destination = safe_next_path(form_data.next_path)
    if authenticate(form_data.username, form_data.password):
        start_admin_session(request)
        return RedirectResponse(url=destination, status_code=303)
    context = {
        "next_path": destination,
        "login_csrf_token": get_csrf_token(request),
        "error": "Invalid username or password",
    }
    return templates.TemplateResponse(
        request=request,
        name="login.html.jinja",
        context=context,
        status_code=401,
    )


@app.post("/logout")
async def logout(
    request: Request, _: None = Depends(require_admin_with_form_csrf)
):
    end_admin_session(request)
    return RedirectResponse(url="/", status_code=303)


@app.exception_handler(StarletteHTTPException)
async def custom_http_exception_handler(
    request: Request, exc: StarletteHTTPException
):
    if exc.status_code == 401 and request.method in {"GET", "HEAD"}:
        next_path = safe_next_path(request.url.path)
        if request.url.query:
            next_path += f"?{request.url.query}"
        return RedirectResponse(
            url=f"/login?next={urllib.parse.quote(next_path, safe='')}",
            status_code=303,
        )
    if exc.status_code == 404:
        return templates.TemplateResponse(
            request=request,
            name="404.html.jinja",
            context={"detail": exc.detail},
            status_code=404,
        )
    if exc.status_code == 500:
        return templates.TemplateResponse(
            request=request,
            name="500.html.jinja",
            context={"detail": exc.detail},
            status_code=500,
        )
    return HTMLResponse(content=str(exc.detail), status_code=exc.status_code)


@app.get("/static/{file_name}", include_in_schema=False)
async def static_file(file_name):
    return FileResponse(f"./static/{file_name}")


QUIZ_EXCLUDE_HISTORY_SIZE = 15


def _next_quiz_question(
    exclude: str, track_visit: bool = False
) -> tuple[Optional[QuizQuestion], str]:
    """Shared by the dashboard's initial render and the JSON route it polls
    for "Try another". Order matters in the exclude list (oldest-first) so
    the trailing slice keeps the *most recently seen* entries, not an
    arbitrary subset."""
    exclude_ids_ordered = [int(x) for x in exclude.split(",") if x.strip().isdigit()]
    exclude_ids_ordered = list(dict.fromkeys(exclude_ids_ordered))

    question = pick_random_question(exclude_entry_ids=set(exclude_ids_ordered))
    if (
        track_visit
        and question
        and db_entry_last_visit_old_enough(question.entry_id)
    ):
        db_entry_increment_visit_count(question.entry_id)

    next_exclude_ids = exclude_ids_ordered + ([question.entry_id] if question else [])
    next_exclude_ids = list(dict.fromkeys(next_exclude_ids))
    next_exclude = ",".join(
        str(i) for i in next_exclude_ids[-QUIZ_EXCLUDE_HISTORY_SIZE:]
    )
    return question, next_exclude


@app.get("/", response_class=HTMLResponse)
async def root_page(request: Request):
    authenticated = is_admin(request)
    review_bookmark_entry_id = get_review_bookmark() if authenticated else None
    seven_days_ago = int(time.time()) - 7 * 86400
    question, next_exclude = _next_quiz_question("", track_visit=authenticated)
    context = {
        "entries_count": db_count_entries(),
        "visited_last_7_days": db_count_entries_visited_since(seven_days_ago),
        "review_bookmark_entry_id": review_bookmark_entry_id,
        "question": question,
        "next_exclude": next_exclude,
    }
    return templates.TemplateResponse(
        request=request, name="root.html.jinja", context=context
    )


@app.get("/quiz/next")
async def quiz_next(request: Request, exclude: str = Query("")):
    question, next_exclude = _next_quiz_question(
        exclude, track_visit=is_admin(request)
    )
    if not question:
        return JSONResponse({"question": None})
    return JSONResponse(
        {
            "entry_id": question.entry_id,
            "word": question.word,
            "blanked_sentence": question.blanked_sentence,
            "next_exclude": next_exclude,
        },
        headers={"Cache-Control": "no-store"},
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
    # Stripped once here to match what db_get_entries_page() actually
    # searched on (it strips internally) - highlight_matches() below needs
    # the same value or a leading/trailing-space query would match rows
    # (DB search already stripped it) but fail to highlight anything.
    q_stripped = q.strip()
    review_bookmark_entry_id = get_review_bookmark() if is_admin(request) else None
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

        # highlight_matches() is a no-op (just escapes) when q is empty, so
        # this always runs rather than branching on whether there's a
        # search - must come after normalize_pronoun_casing() above, never
        # before (see that function's docstring).
        display_text = highlight_matches(display_text, q_stripped)
        context_text = highlight_matches(context_text, q_stripped)
        if show_example and entry.example:
            entry = replace(entry, example=highlight_matches(entry.example, q_stripped))

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

    # Live search (static/script.js, initLiveSearch): the same route,
    # tagged with this header instead of a separate endpoint, so the query
    # logic above doesn't have to be duplicated. Returns just the bits the
    # page updates in place, rendering the table/pagination via the same
    # partial the full page includes.
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        results_html = templates.env.get_template(
            "_entries_results.html.jinja"
        ).render(context)
        return JSONResponse(
            {
                "count": total_count,
                "matching": bool(q_stripped),
                "query": q_stripped,
                "results_html": results_html,
            },
            headers={"Cache-Control": "no-store"},
        )

    return templates.TemplateResponse(
        request=request, name="entries.html.jinja", context=context
    )


@app.get("/entry/{entry_id}", response_class=HTMLResponse)
async def entry_page(entry_id: int, request: Request):
    entry = db_get_entry_by_id(entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    visit_count = entry.visit_count
    if is_admin(request) and db_entry_last_visit_old_enough(entry.id):
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
async def edit_entry_page(
    entry_id: int, request: Request, _: None = Depends(require_admin)
):
    entry = db_get_entry_by_id(entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")

    context = {"entry_id": entry_id, "entry_text": entry.text, "needs_editor": True}
    return templates.TemplateResponse(
        request=request, name="edit_entry.html.jinja", context=context
    )


@app.get("/edit_definition/{definition_id}", response_class=HTMLResponse)
async def edit_definition_page(
    definition_id: int, request: Request, _: None = Depends(require_admin)
):
    definition = db_get_definition_by_id(definition_id)
    if not definition:
        raise HTTPException(status_code=404, detail="Definition not found")
    context = {
        "definition_text": definition.text,
        "definition_id": definition_id,
        "entry_id": definition.question_id,
        "needs_editor": True,
    }
    return templates.TemplateResponse(
        request=request, name="edit_definition.html.jinja", context=context
    )


@app.get("/edit_example/{entry_id}", response_class=HTMLResponse)
async def edit_example_page(
    entry_id: int, request: Request, _: None = Depends(require_admin)
):
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
async def add_entry_page(request: Request, _: None = Depends(require_admin)):
    return templates.TemplateResponse(
        request=request,
        name="add_entry.html.jinja",
        context={"needs_editor": True},
    )


@app.get("/add_definition", response_class=HTMLResponse)
async def add_definition_page(
    entry_id: int, request: Request, _: None = Depends(require_admin)
):
    context = {"entry_id": entry_id, "needs_editor": True}
    return templates.TemplateResponse(
        request=request, name="add_definition.html.jinja", context=context
    )


@app.post("/edit_entry/{entry_id}", response_class=HTMLResponse)
async def edit_entry(
    entry_id: int,
    request: Request,
    form_data: EditEntryForm = Depends(EditEntryForm.as_form),
    _: None = Depends(require_admin),
):
    verify_csrf_value(request, form_data.csrf_token)
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
    request: Request,
    form_data: EditDefinitionForm = Depends(EditDefinitionForm.as_form),
    _: None = Depends(require_admin),
):
    verify_csrf_value(request, form_data.csrf_token)
    updated_text = form_data.definition_text
    if entry_id := db_update_definition_text(definition_id, updated_text):
        return RedirectResponse(url=f"/entry/{entry_id}", status_code=303)


@app.post("/edit_example/{entry_id}", response_class=HTMLResponse)
async def edit_example(
    entry_id: int,
    request: Request,
    form_data: EditExampleForm = Depends(EditExampleForm.as_form),
    _: None = Depends(require_admin),
):
    verify_csrf_value(request, form_data.csrf_token)
    if not (updated_text := form_data.example_text):
        updated_text = ""
    if updated_eid := db_update_example(entry_id, updated_text):
        invalidate_quiz_pool_cache()
        return RedirectResponse(url=f"/entry/{updated_eid}", status_code=303)


@app.delete("/delete_entry/{entry_id}")
async def delete_entry(
    entry_id: int, _: None = Depends(require_admin_with_header_csrf)
):
    db_delete_entry(entry_id)
    invalidate_words_cache()
    invalidate_quiz_pool_cache()
    return {"message": "deleted"}


@app.delete("/delete_definition/{definition_id}", response_class=HTMLResponse)
async def delete_definition(
    definition_id: int, _: None = Depends(require_admin_with_header_csrf)
):
    if entry_id := db_delete_definition(definition_id):
        return RedirectResponse(url=f"/entry/{entry_id}", status_code=303)


@app.post("/add_entry", response_class=HTMLResponse)
async def add_entry(
    request: Request,
    form_data: AddEntryForm = Depends(AddEntryForm.as_form),
    _: None = Depends(require_admin),
):
    verify_csrf_value(request, form_data.csrf_token)
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
    request: Request,
    form_data: AddDefinitionForm = Depends(AddDefinitionForm.as_form),
    _: None = Depends(require_admin),
):
    verify_csrf_value(request, form_data.csrf_token)
    updated_text = form_data.definition_text
    entry_id = form_data.entry_id
    if entry := db_get_entry_by_id(entry_id):
        db_add_definition(updated_text, entry=entry)
        return RedirectResponse(url=f"/entry/{entry_id}", status_code=303)
    raise HTTPException(status_code=404, detail="Entry not found")


@app.post("/entry/{entry_id}/set_review_bookmark")
async def set_review_bookmark(
    entry_id: int, _: None = Depends(require_admin_with_header_csrf)
):
    success = db_set_review_bookmark(entry_id)
    if not success:
        raise HTTPException(status_code=404, detail="Entry not found")
    return {"message": "Review bookmark set"}


@app.post("/entry/{entry_id}/clear_review_bookmark")
async def clear_review_bookmark(
    entry_id: int, _: None = Depends(require_admin_with_header_csrf)
):
    success = db_clear_review_bookmark(entry_id)
    if not success:
        raise HTTPException(status_code=404, detail="Entry not found")
    return {"message": "Review bookmark cleared"}


@app.get("/review_bookmark")
async def review_bookmark(_: None = Depends(require_admin)):
    return JSONResponse(
        {"entry_id": get_review_bookmark()},
        headers={"Cache-Control": "no-store"},
    )


@app.get("/resume_review")
async def resume_review(_: None = Depends(require_admin)):
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
async def notes(request: Request, _: None = Depends(require_admin)):
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
def view_note(
    note_path: str, request: Request, _: None = Depends(require_admin)
) -> _TemplateResponse:
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
async def edit_note_page(
    note_path: str, request: Request, _: None = Depends(require_admin)
):
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
    _: None = Depends(require_admin),
):
    verify_csrf_value(request, form_data.csrf_token)
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
