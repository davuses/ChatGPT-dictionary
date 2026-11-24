import hashlib
import logging
import time
import urllib.parse
from contextlib import asynccontextmanager
from dataclasses import asdict, replace
from functools import lru_cache
from pathlib import Path
from typing import Optional

import markdown2
from fastapi import APIRouter, Depends, FastAPI, Form, HTTPException, Query, Request
from fastapi.responses import (
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
    check_auth_rate_limit,
    clear_auth_failures,
    end_user_session,
    generate_opaque_token,
    get_auth_settings,
    get_csrf_token,
    get_current_user,
    hash_password,
    record_auth_failure,
    require_admin,
    require_user,
    safe_next_path,
    start_user_session,
    validate_password,
    validate_username,
    verify_csrf_value,
    verify_form_csrf,
    verify_header_csrf,
    verify_password,
)
from database import (
    ENTRIES_PAGE_SIZE,
    UserRecord,
    bootstrap_database,
    db_add_definition,
    db_add_entry,
    db_clear_review_bookmark,
    db_count_active_admins,
    db_count_entries,
    db_count_entries_visited_since,
    db_count_undefined_entries,
    db_create_api_token,
    db_create_invite_token,
    db_create_password_reset_token,
    db_delete_definition,
    db_delete_entry,
    db_get_definition_by_id,
    db_get_entries_page,
    db_get_entry_by_id,
    db_get_entry_by_text,
    db_get_entry_page_number,
    db_get_user_by_id,
    db_get_user_with_password_by_username,
    db_get_valid_invite_token,
    db_get_valid_password_reset_token,
    db_list_api_tokens,
    db_list_invite_tokens,
    db_list_page_notes,
    db_list_users_for_admin,
    db_record_entry_visit,
    db_redeem_invite_and_create_user,
    db_redeem_password_reset,
    db_revoke_api_token,
    db_revoke_invite_token,
    db_set_review_bookmark,
    db_set_user_active,
    db_update_definition_text,
    db_update_entry_text,
    db_update_example,
    db_update_user_password,
    get_review_bookmark,
    hash_token,
)
from utils import (
    EntryDisplay,
    QuizQuestion,
    build_directory_tree_markdown,
    get_all_words,
    get_how_long_ago,
    get_IPA,
    get_notes_dir,
    get_thesaurus_senses,
    highlight_matches,
    invalidate_quiz_pool_cache,
    invalidate_words_cache,
    normalize_pronoun_casing,
    parse_entry_text,
    pick_random_question,
    pick_review_session,
    render_safe_markdown,
    safe_path_note,
    validate_entry_fields,
)

logger = logging.getLogger(__name__)
auth_settings = get_auth_settings()

INVITE_TTL_SECONDS = 7 * 24 * 60 * 60
PASSWORD_RESET_TTL_SECONDS = 24 * 60 * 60
_SENSITIVE_TOKEN_HEADERS = {
    "Cache-Control": "no-store",
    "Referrer-Policy": "no-referrer",
}


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings = get_auth_settings()
    bootstrap_database(
        admin_username=settings.username,
        admin_password_hash=settings.password_hash,
        legacy_api_token=settings.api_token,
    )
    yield


app = FastAPI(
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    lifespan=lifespan,
)
app.add_middleware(
    SessionMiddleware,
    secret_key=auth_settings.session_secret,
    session_cookie="dictionary_session",
    max_age=SESSION_MAX_AGE,
    same_site="lax",
    https_only=auth_settings.https_only,
)


STATIC_DIR = Path(__file__).resolve().parent / "static"


@lru_cache(maxsize=64)
def static_url(filename: str) -> str:
    clean_name = filename.lstrip("/")
    file_path = (STATIC_DIR / clean_name).resolve()
    if file_path.is_relative_to(STATIC_DIR) and file_path.is_file():
        digest = hashlib.sha256(file_path.read_bytes()).hexdigest()[:12]
        return f"/static/{clean_name}?v={digest}"
    return f"/static/{clean_name}"


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(
    directory=str(TEMPLATES_DIR), context_processors=[auth_template_context]
)
templates.env.globals["static_url"] = static_url
templates.env.globals["how_long_ago"] = get_how_long_ago

protected_router = APIRouter(dependencies=[Depends(require_user)])
admin_router = APIRouter(dependencies=[Depends(require_admin)])


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
    word: str = ""
    context: str = ""

    @classmethod
    async def as_form(
        cls,
        word: str = Form(""),
        context: str = Form(""),
        csrf_token: str = Form(...),
    ):
        return cls(word=word, context=context, csrf_token=csrf_token)


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
    word: str = ""
    context: str = ""
    definition_text: str = ""
    example_text: str = ""

    @classmethod
    async def as_form(
        cls,
        word: str = Form(""),
        context: str = Form(""),
        definition_text: str = Form(""),
        example_text: str = Form(""),
        csrf_token: str = Form(...),
    ):
        return cls(
            word=word,
            context=context,
            definition_text=definition_text,
            example_text=example_text,
            csrf_token=csrf_token,
        )


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


class RegisterForm(CsrfForm):
    code: str
    username: str
    password: str
    confirm_password: str

    @classmethod
    async def as_form(
        cls,
        code: str = Form(""),
        username: str = Form(""),
        password: str = Form(""),
        confirm_password: str = Form(""),
        csrf_token: str = Form(...),
    ):
        return cls(
            code=code,
            username=username,
            password=password,
            confirm_password=confirm_password,
            csrf_token=csrf_token,
        )


class ResetPasswordForm(CsrfForm):
    token: str
    password: str
    confirm_password: str

    @classmethod
    async def as_form(
        cls,
        token: str = Form(""),
        password: str = Form(""),
        confirm_password: str = Form(""),
        csrf_token: str = Form(...),
    ):
        return cls(
            token=token,
            password=password,
            confirm_password=confirm_password,
            csrf_token=csrf_token,
        )


class ChangePasswordForm(CsrfForm):
    current_password: str
    new_password: str
    confirm_password: str

    @classmethod
    async def as_form(
        cls,
        current_password: str = Form(""),
        new_password: str = Form(""),
        confirm_password: str = Form(""),
        csrf_token: str = Form(...),
    ):
        return cls(
            current_password=current_password,
            new_password=new_password,
            confirm_password=confirm_password,
            csrf_token=csrf_token,
        )


class CreateApiTokenForm(CsrfForm):
    label: str = ""

    @classmethod
    async def as_form(
        cls,
        label: str = Form(""),
        csrf_token: str = Form(...),
    ):
        return cls(label=label, csrf_token=csrf_token)


class CreateInviteForm(CsrfForm):
    note: str = ""

    @classmethod
    async def as_form(
        cls,
        note: str = Form(""),
        csrf_token: str = Form(...),
    ):
        return cls(note=note, csrf_token=csrf_token)


# ---------------------------------------------------------------------------
# Public authentication routes
# ---------------------------------------------------------------------------


@app.get("/login", response_class=HTMLResponse)
async def login_page(
    request: Request,
    next_path: str = Query("/", alias="next"),
    reset: Optional[str] = Query(None),
):
    destination = safe_next_path(next_path)
    if get_current_user(request) is not None:
        return RedirectResponse(url=destination, status_code=303)
    context = {
        "next_path": destination,
        "login_csrf_token": get_csrf_token(request),
        "error": None,
        "notice": "Password updated. You can log in now." if reset else None,
    }
    return templates.TemplateResponse(
        request=request, name="login.html.jinja", context=context
    )


@app.post("/login", response_class=HTMLResponse)
def login(
    request: Request,
    form_data: LoginForm = Depends(LoginForm.as_form),
):
    verify_csrf_value(request, form_data.csrf_token)
    destination = safe_next_path(form_data.next_path)
    if check_auth_rate_limit(request, "login", form_data.username):
        return templates.TemplateResponse(
            request=request,
            name="login.html.jinja",
            context={
                "next_path": destination,
                "login_csrf_token": get_csrf_token(request),
                "error": "Too many login attempts. Please wait a few minutes.",
                "notice": None,
            },
            status_code=429,
        )
    user = authenticate(form_data.username, form_data.password)
    if user is not None:
        clear_auth_failures(request, "login", form_data.username)
        start_user_session(request, user)
        return RedirectResponse(url=destination, status_code=303)
    record_auth_failure(request, "login", form_data.username)
    context = {
        "next_path": destination,
        "login_csrf_token": get_csrf_token(request),
        "error": "Invalid username or password",
        "notice": None,
    }
    return templates.TemplateResponse(
        request=request,
        name="login.html.jinja",
        context=context,
        status_code=401,
    )


@app.get("/register", response_class=HTMLResponse, name="register_page")
async def register_page(request: Request, code: str = Query("")):
    clean_code = code.strip()
    invite = db_get_valid_invite_token(hash_token(clean_code)) if clean_code else None
    context = {
        "code": clean_code,
        "invite_valid": invite is not None,
        "username": "",
        "form_csrf_token": get_csrf_token(request),
        "error": (
            None
            if invite is not None
            else (
                "This invite link is invalid, expired, or has already been used."
                if clean_code
                else "Registration is invite-only. Ask the admin for an invite link."
            )
        ),
    }
    return templates.TemplateResponse(
        request=request,
        name="register.html.jinja",
        context=context,
        headers=_SENSITIVE_TOKEN_HEADERS,
    )


@app.post("/register", response_class=HTMLResponse)
def register(
    request: Request,
    form_data: RegisterForm = Depends(RegisterForm.as_form),
):
    verify_csrf_value(request, form_data.csrf_token)
    clean_code = form_data.code.strip()

    def _render_error(message: str, status_code: int = 400, invite_valid: bool = True):
        return templates.TemplateResponse(
            request=request,
            name="register.html.jinja",
            context={
                "code": clean_code,
                "invite_valid": invite_valid,
                "username": form_data.username,
                "form_csrf_token": get_csrf_token(request),
                "error": message,
            },
            status_code=status_code,
            headers=_SENSITIVE_TOKEN_HEADERS,
        )

    if check_auth_rate_limit(request, "register", form_data.username):
        return _render_error(
            "Too many registration attempts. Please wait a few minutes.",
            status_code=429,
        )

    if not clean_code:
        record_auth_failure(request, "register", form_data.username)
        return _render_error("An invite code is required.", invite_valid=False)

    clean_username, username_error = validate_username(form_data.username)
    if username_error or not clean_username:
        return _render_error(username_error or "Invalid username.")

    if form_data.password != form_data.confirm_password:
        return _render_error("Passwords do not match.")

    password_error = validate_password(form_data.password)
    if password_error:
        return _render_error(password_error)

    token_digest = hash_token(clean_code)
    if db_get_valid_invite_token(token_digest) is None:
        record_auth_failure(request, "register", form_data.username)
        return _render_error(
            "This invite link is invalid, expired, or has already been used.",
            status_code=400,
            invite_valid=False,
        )

    user, err = db_redeem_invite_and_create_user(
        token_digest, clean_username, hash_password(form_data.password)
    )
    if err or user is None:
        record_auth_failure(request, "register", clean_username)
        is_taken = "already taken" in (err or "").lower()
        return _render_error(
            err or "Unable to complete registration.",
            status_code=409 if is_taken else 400,
            invite_valid=is_taken,
        )

    clear_auth_failures(request, "register", clean_username)
    start_user_session(request, user)
    return RedirectResponse(url="/", status_code=303)


@app.get("/reset-password", response_class=HTMLResponse, name="reset_password_page")
async def reset_password_page(request: Request, token: str = Query("")):
    clean_token = token.strip()
    valid = (
        db_get_valid_password_reset_token(hash_token(clean_token))
        if clean_token
        else None
    )
    context = {
        "token": clean_token,
        "token_valid": valid is not None,
        "target_username": valid[1] if valid else None,
        "form_csrf_token": get_csrf_token(request),
        "error": (
            None
            if valid is not None
            else "This password reset link is invalid, expired, or has already been used."
        ),
    }
    return templates.TemplateResponse(
        request=request,
        name="reset_password.html.jinja",
        context=context,
        headers=_SENSITIVE_TOKEN_HEADERS,
    )


@app.post("/reset-password", response_class=HTMLResponse)
def reset_password(
    request: Request,
    form_data: ResetPasswordForm = Depends(ResetPasswordForm.as_form),
):
    verify_csrf_value(request, form_data.csrf_token)
    clean_token = form_data.token.strip()

    def _render_error(
        message: str,
        status_code: int = 400,
        token_valid: bool = True,
        target_username: str | None = None,
    ):
        return templates.TemplateResponse(
            request=request,
            name="reset_password.html.jinja",
            context={
                "token": clean_token,
                "token_valid": token_valid,
                "target_username": target_username,
                "form_csrf_token": get_csrf_token(request),
                "error": message,
            },
            status_code=status_code,
            headers=_SENSITIVE_TOKEN_HEADERS,
        )

    if check_auth_rate_limit(request, "reset"):
        return _render_error(
            "Too many password reset attempts. Please wait a few minutes.",
            status_code=429,
        )

    valid = (
        db_get_valid_password_reset_token(hash_token(clean_token))
        if clean_token
        else None
    )
    if valid is None:
        record_auth_failure(request, "reset")
        return _render_error(
            "This password reset link is invalid, expired, or has already been used.",
            token_valid=False,
        )
    _, target_username = valid

    if form_data.password != form_data.confirm_password:
        return _render_error(
            "Passwords do not match.", target_username=target_username
        )

    password_error = validate_password(form_data.password)
    if password_error:
        return _render_error(password_error, target_username=target_username)

    user, err = db_redeem_password_reset(
        hash_token(clean_token), hash_password(form_data.password)
    )
    if err or user is None:
        record_auth_failure(request, "reset")
        return _render_error(
            err or "Password reset link is invalid, expired, or already used.",
            token_valid=False,
        )

    end_user_session(request)
    return RedirectResponse(url="/login?reset=1", status_code=303)


@protected_router.post("/logout")
async def logout(request: Request, _: None = Depends(verify_form_csrf)):
    end_user_session(request)
    return RedirectResponse(url="/login", status_code=303)


# ---------------------------------------------------------------------------
# Exception handling
# ---------------------------------------------------------------------------


def _wants_json_error(request: Request) -> bool:
    if request.url.path.startswith("/api/"):
        return True
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return True
    sec_fetch_mode = request.headers.get("Sec-Fetch-Mode")
    if sec_fetch_mode and sec_fetch_mode != "navigate":
        return True
    accept = request.headers.get("Accept", "")
    if "application/json" in accept and "text/html" not in accept:
        return True
    route = request.scope.get("route")
    route_response_class = getattr(route, "response_class", None)
    route_response_class = getattr(route_response_class, "value", route_response_class)
    if route_response_class is not None and route_response_class not in (
        HTMLResponse,
        RedirectResponse,
    ):
        return True
    return False


@app.exception_handler(StarletteHTTPException)
async def custom_http_exception_handler(
    request: Request, exc: StarletteHTTPException
):
    if exc.status_code == 401:
        if request.method in {"GET", "HEAD"} and not _wants_json_error(request):
            next_path = safe_next_path(request.url.path)
            if request.url.query:
                next_path += f"?{request.url.query}"
            return RedirectResponse(
                url=f"/login?next={urllib.parse.quote(next_path, safe='')}",
                status_code=303,
            )
        return JSONResponse(
            {"detail": exc.detail},
            status_code=401,
            headers=exc.headers,
        )
    if _wants_json_error(request):
        return JSONResponse(
            {"detail": exc.detail},
            status_code=exc.status_code,
            headers=exc.headers,
        )
    if exc.status_code == 403:
        return templates.TemplateResponse(
            request=request,
            name="403.html.jinja",
            context={"detail": exc.detail},
            status_code=403,
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


# ---------------------------------------------------------------------------
# User-scoped dictionary, quiz, bookmark, inbox, and account routes
# ---------------------------------------------------------------------------

QUIZ_EXCLUDE_HISTORY_SIZE = 15


def _next_quiz_question(
    user_id: int, exclude: str
) -> tuple[Optional[QuizQuestion], str]:
    exclude_ids_ordered = [int(x) for x in exclude.split(",") if x.strip().isdigit()]
    exclude_ids_ordered = list(dict.fromkeys(exclude_ids_ordered))

    question = pick_random_question(
        user_id, exclude_entry_ids=set(exclude_ids_ordered)
    )

    next_exclude_ids = exclude_ids_ordered + ([question.entry_id] if question else [])
    next_exclude_ids = list(dict.fromkeys(next_exclude_ids))
    next_exclude = ",".join(
        str(i) for i in next_exclude_ids[-QUIZ_EXCLUDE_HISTORY_SIZE:]
    )
    return question, next_exclude


@protected_router.get("/", response_class=HTMLResponse)
def root_page(
    request: Request,
    current_user: UserRecord = Depends(require_user),
):
    review_bookmark_entry_id = get_review_bookmark(current_user.id)
    seven_days_ago = int(time.time()) - 7 * 86400
    question, next_exclude = _next_quiz_question(current_user.id, "")
    context = {
        "entries_count": db_count_entries(current_user.id),
        "visited_last_7_days": db_count_entries_visited_since(
            current_user.id, seven_days_ago
        ),
        "review_bookmark_entry_id": review_bookmark_entry_id,
        "question": question,
        "next_exclude": next_exclude,
    }
    return templates.TemplateResponse(
        request=request, name="root.html.jinja", context=context
    )


@protected_router.get("/quiz/next", response_class=JSONResponse)
def quiz_next(
    exclude: str = Query(""),
    current_user: UserRecord = Depends(require_user),
):
    question, next_exclude = _next_quiz_question(current_user.id, exclude)
    if not question:
        return JSONResponse(
            {"question": None}, headers={"Cache-Control": "no-store"}
        )
    return JSONResponse(
        {
            "entry_id": question.entry_id,
            "word": question.word,
            "blanked_sentence": question.blanked_sentence,
            "next_exclude": next_exclude,
        },
        headers={"Cache-Control": "no-store"},
    )


@protected_router.post("/quiz/{entry_id}/seen")
def quiz_mark_seen(
    entry_id: int,
    _: None = Depends(verify_header_csrf),
    current_user: UserRecord = Depends(require_user),
):
    recorded = db_record_entry_visit(current_user.id, entry_id)
    if recorded is None:
        raise HTTPException(status_code=404, detail="Entry not found")
    return {"recorded": recorded}


REVIEW_DEFAULT_SIZE = 10
REVIEW_EXCLUDE_HISTORY_SIZE = 40


@protected_router.get("/review", response_class=HTMLResponse)
def review_page(
    request: Request,
    size: int = Query(REVIEW_DEFAULT_SIZE, ge=1, le=25),
    exclude: str = Query(""),
    current_user: UserRecord = Depends(require_user),
):
    exclude_ids_ordered = [
        int(x) for x in exclude.split(",") if x.strip().isdigit()
    ]
    exclude_ids_ordered = list(dict.fromkeys(exclude_ids_ordered))

    cards, total_quizzable = pick_review_session(
        current_user.id,
        limit=size,
        exclude_entry_ids=set(exclude_ids_ordered),
    )
    combined_exclude = list(
        dict.fromkeys(exclude_ids_ordered + [c.entry_id for c in cards])
    )
    next_exclude = ",".join(
        str(eid) for eid in combined_exclude[-REVIEW_EXCLUDE_HISTORY_SIZE:]
    )

    another_round_params: dict[str, str | int] = {}
    if size != REVIEW_DEFAULT_SIZE:
        another_round_params["size"] = size
    if next_exclude:
        another_round_params["exclude"] = next_exclude
    another_round_url = "/review" + (
        "?" + urllib.parse.urlencode(another_round_params)
        if another_round_params
        else ""
    )

    context = {
        "cards_json": [asdict(card) for card in cards],
        "card_count": len(cards),
        "total_quizzable": total_quizzable,
        "session_size": size,
        "another_round_url": another_round_url,
        "needs_markdown_css": True,
    }
    return templates.TemplateResponse(
        request=request,
        name="review.html.jinja",
        context=context,
        headers={"Cache-Control": "private, no-cache"},
    )


@protected_router.get("/entries", response_class=HTMLResponse)
def entries_page(
    request: Request,
    show_example: bool = Query(False),
    entries_only: bool = Query(False),
    needs_definition: bool = Query(False),
    q: str = Query(""),
    page: int = Query(1, ge=1),
    current_user: UserRecord = Depends(require_user),
):
    if needs_definition:
        entries_only = False
        show_example = False
    elif entries_only:
        show_example = False

    entries, total_count = db_get_entries_page(
        current_user.id,
        query=q,
        include_examples=show_example,
        needs_definition=needs_definition,
        page=page,
    )
    total_pages = max(1, -(-total_count // ENTRIES_PAGE_SIZE))
    if page > total_pages:
        page = total_pages
        if total_count > 0:
            entries, total_count = db_get_entries_page(
                current_user.id,
                query=q,
                include_examples=show_example,
                needs_definition=needs_definition,
                page=page,
            )
    q_stripped = q.strip()
    is_xhr = request.headers.get("X-Requested-With") == "XMLHttpRequest"
    if is_xhr:
        undefined_count = 0
    elif needs_definition and not q_stripped:
        undefined_count = total_count
    else:
        undefined_count = db_count_undefined_entries(current_user.id)

    review_bookmark_entry_id = get_review_bookmark(current_user.id)
    entry_displays: list[EntryDisplay] = []
    for entry in entries:
        context_text, display_text = parse_entry_text(entry.text)
        context_text = normalize_pronoun_casing(context_text)

        if show_example and entry.example:
            entry = replace(entry, example=normalize_pronoun_casing(entry.example))

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

    context = {
        "entries_count": total_count,
        "entry_displays": entry_displays,
        "entries_only": entries_only,
        "show_example": show_example,
        "needs_definition": needs_definition,
        "undefined_count": undefined_count,
        "review_bookmark_entry_id": review_bookmark_entry_id,
        "search_query": q,
        "page": page,
        "total_pages": total_pages,
        "has_prev_page": page > 1,
        "has_next_page": page < total_pages,
    }

    if is_xhr:
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


@protected_router.get("/entry/{entry_id}", response_class=HTMLResponse)
def entry_page(
    entry_id: int,
    request: Request,
    current_user: UserRecord = Depends(require_user),
):
    entry = db_get_entry_by_id(current_user.id, entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    visit_count = entry.visit_count or 0
    if db_record_entry_visit(current_user.id, entry.id):
        visit_count += 1
    definition_exists = bool(entry.definitions)
    definition_html = None
    definition_id = None
    if definition_exists:
        d = entry.definitions[0]
        definition_html = render_safe_markdown(d.text, extras=["strike"])
        definition_id = d.id
    context_text, word = parse_entry_text(entry.text)
    IPA_transcript = get_IPA(word)
    oxford_audio_slug = urllib.parse.quote(word.lower(), safe="")
    tts_audio_query = urllib.parse.quote_plus(word)
    example_html = (
        render_safe_markdown(
            normalize_pronoun_casing(entry.example),
            extras=["strike", "tables"],
            wrap_ipa=True,
        )
        if entry.example
        else ""
    )
    review_bookmark_entry_id = get_review_bookmark(current_user.id)
    context = {
        "visit_count": visit_count,
        "last_visit_elapsed": get_how_long_ago(entry.last_visit),
        "is_review_bookmark": entry_id == review_bookmark_entry_id,
        "entry_text": normalize_pronoun_casing(entry.text),
        "context_text": normalize_pronoun_casing(context_text),
        "entry_id": entry_id,
        "IPA_transcript": IPA_transcript,
        "word": word,
        "oxford_audio_slug": oxford_audio_slug,
        "tts_audio_query": tts_audio_query,
        "definition_exists": definition_exists,
        "definition_html": definition_html,
        "definition_id": definition_id,
        "example_html": example_html,
        "needs_markdown_css": True,
    }
    return templates.TemplateResponse(
        request=request, name="entry.html.jinja", context=context
    )


@protected_router.get("/edit_entry/{entry_id}", response_class=HTMLResponse)
def edit_entry_page(
    entry_id: int,
    request: Request,
    current_user: UserRecord = Depends(require_user),
):
    entry = db_get_entry_by_id(current_user.id, entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")

    context_text, word = parse_entry_text(entry.text)
    context = {
        "entry_id": entry_id,
        "word": word,
        "context": context_text,
        "error": None,
        "existing_entry_id": None,
    }
    return templates.TemplateResponse(
        request=request, name="edit_entry.html.jinja", context=context
    )


@protected_router.get("/edit_definition/{definition_id}", response_class=HTMLResponse)
def edit_definition_page(
    definition_id: int,
    request: Request,
    current_user: UserRecord = Depends(require_user),
):
    definition = db_get_definition_by_id(current_user.id, definition_id)
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


@protected_router.get("/edit_example/{entry_id}", response_class=HTMLResponse)
def edit_example_page(
    entry_id: int,
    request: Request,
    current_user: UserRecord = Depends(require_user),
):
    entry = db_get_entry_by_id(current_user.id, entry_id)
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


@protected_router.get("/add_entry", response_class=HTMLResponse)
async def add_entry_page(request: Request):
    context = {
        "word": "",
        "context": "",
        "definition_text": "",
        "example_text": "",
        "error": None,
        "existing_entry_id": None,
    }
    return templates.TemplateResponse(
        request=request,
        name="add_entry.html.jinja",
        context=context,
    )


@protected_router.get("/add_definition", response_class=HTMLResponse)
def add_definition_page(
    entry_id: int,
    request: Request,
    current_user: UserRecord = Depends(require_user),
):
    if not db_get_entry_by_id(current_user.id, entry_id):
        raise HTTPException(status_code=404, detail="Entry not found")
    context = {"entry_id": entry_id, "needs_editor": True}
    return templates.TemplateResponse(
        request=request, name="add_definition.html.jinja", context=context
    )


@protected_router.post("/edit_entry/{entry_id}", response_class=HTMLResponse)
def edit_entry(
    entry_id: int,
    request: Request,
    form_data: EditEntryForm = Depends(EditEntryForm.as_form),
    current_user: UserRecord = Depends(require_user),
):
    verify_csrf_value(request, form_data.csrf_token)
    updated_text, error = validate_entry_fields(form_data.word, form_data.context)
    if error or not updated_text:
        return templates.TemplateResponse(
            request=request,
            name="edit_entry.html.jinja",
            context={
                "entry_id": entry_id,
                "word": form_data.word,
                "context": form_data.context,
                "error": error,
                "existing_entry_id": None,
            },
            status_code=400,
        )
    try:
        if e_id := db_update_entry_text(current_user.id, entry_id, updated_text):
            invalidate_words_cache(current_user.id)
            invalidate_quiz_pool_cache(current_user.id)
            return RedirectResponse(url=f"/entry/{e_id}", status_code=303)
    except IntegrityError:
        existing = db_get_entry_by_text(current_user.id, updated_text)
        return templates.TemplateResponse(
            request=request,
            name="edit_entry.html.jinja",
            context={
                "entry_id": entry_id,
                "word": form_data.word,
                "context": form_data.context,
                "error": "An entry with that text already exists.",
                "existing_entry_id": existing.id if existing else None,
            },
            status_code=409,
        )
    raise HTTPException(status_code=404, detail="Entry not found")


@protected_router.post("/edit_definition/{definition_id}", response_class=HTMLResponse)
def edit_definition(
    definition_id: int,
    request: Request,
    form_data: EditDefinitionForm = Depends(EditDefinitionForm.as_form),
    current_user: UserRecord = Depends(require_user),
):
    verify_csrf_value(request, form_data.csrf_token)
    updated_text = form_data.definition_text.strip()
    if not updated_text:
        raise HTTPException(status_code=400, detail="Definition cannot be empty")
    if entry_id := db_update_definition_text(
        current_user.id, definition_id, updated_text
    ):
        return RedirectResponse(url=f"/entry/{entry_id}", status_code=303)
    raise HTTPException(status_code=404, detail="Definition not found")


@protected_router.post("/edit_example/{entry_id}", response_class=HTMLResponse)
def edit_example(
    entry_id: int,
    request: Request,
    form_data: EditExampleForm = Depends(EditExampleForm.as_form),
    current_user: UserRecord = Depends(require_user),
):
    verify_csrf_value(request, form_data.csrf_token)
    if not (updated_text := form_data.example_text):
        updated_text = ""
    if updated_eid := db_update_example(current_user.id, entry_id, updated_text):
        invalidate_quiz_pool_cache(current_user.id)
        return RedirectResponse(url=f"/entry/{updated_eid}", status_code=303)
    raise HTTPException(status_code=404, detail="Entry not found")


@protected_router.delete("/delete_entry/{entry_id}")
def delete_entry(
    entry_id: int,
    _: None = Depends(verify_header_csrf),
    current_user: UserRecord = Depends(require_user),
):
    if not db_delete_entry(current_user.id, entry_id):
        raise HTTPException(status_code=404, detail="Entry not found")
    invalidate_words_cache(current_user.id)
    invalidate_quiz_pool_cache(current_user.id)
    return {"message": "deleted"}


@protected_router.delete("/delete_definition/{definition_id}")
def delete_definition(
    definition_id: int,
    _: None = Depends(verify_header_csrf),
    current_user: UserRecord = Depends(require_user),
):
    if not db_delete_definition(current_user.id, definition_id):
        raise HTTPException(status_code=404, detail="Definition not found")
    return {"message": "deleted"}


@protected_router.post("/add_entry", response_class=HTMLResponse)
def add_entry(
    request: Request,
    form_data: AddEntryForm = Depends(AddEntryForm.as_form),
    current_user: UserRecord = Depends(require_user),
):
    verify_csrf_value(request, form_data.csrf_token)
    updated_text, error = validate_entry_fields(form_data.word, form_data.context)
    if error or not updated_text:
        return templates.TemplateResponse(
            request=request,
            name="add_entry.html.jinja",
            context={
                "word": form_data.word,
                "context": form_data.context,
                "definition_text": form_data.definition_text,
                "example_text": form_data.example_text,
                "error": error,
                "existing_entry_id": None,
            },
            status_code=400,
        )
    try:
        if e_id := db_add_entry(
            current_user.id,
            updated_text,
            definition_text=form_data.definition_text,
            example_text=form_data.example_text,
        ):
            invalidate_words_cache(current_user.id)
            invalidate_quiz_pool_cache(current_user.id)
            return RedirectResponse(url=f"/entry/{e_id}", status_code=303)
    except IntegrityError:
        existing = db_get_entry_by_text(current_user.id, updated_text)
        return templates.TemplateResponse(
            request=request,
            name="add_entry.html.jinja",
            context={
                "word": form_data.word,
                "context": form_data.context,
                "definition_text": form_data.definition_text,
                "example_text": form_data.example_text,
                "error": "An entry with that text already exists.",
                "existing_entry_id": existing.id if existing else None,
            },
            status_code=409,
        )


@protected_router.post("/add_definition", response_class=HTMLResponse)
def add_definition(
    request: Request,
    form_data: AddDefinitionForm = Depends(AddDefinitionForm.as_form),
    current_user: UserRecord = Depends(require_user),
):
    verify_csrf_value(request, form_data.csrf_token)
    updated_text = form_data.definition_text.strip()
    if not updated_text:
        raise HTTPException(status_code=400, detail="Definition cannot be empty")
    entry_id = form_data.entry_id
    if db_add_definition(current_user.id, entry_id, updated_text) is not None:
        return RedirectResponse(url=f"/entry/{entry_id}", status_code=303)
    raise HTTPException(status_code=404, detail="Entry not found")


@protected_router.post("/entry/{entry_id}/set_review_bookmark")
def set_review_bookmark(
    entry_id: int,
    _: None = Depends(verify_header_csrf),
    current_user: UserRecord = Depends(require_user),
):
    success = db_set_review_bookmark(current_user.id, entry_id)
    if not success:
        raise HTTPException(status_code=404, detail="Entry not found")
    return {"message": "Review bookmark set"}


@protected_router.post("/entry/{entry_id}/clear_review_bookmark")
def clear_review_bookmark(
    entry_id: int,
    _: None = Depends(verify_header_csrf),
    current_user: UserRecord = Depends(require_user),
):
    success = db_clear_review_bookmark(current_user.id, entry_id)
    if not success:
        raise HTTPException(status_code=404, detail="Entry not found")
    return {"message": "Review bookmark cleared"}


@protected_router.get("/review_bookmark", response_class=JSONResponse)
def review_bookmark(current_user: UserRecord = Depends(require_user)):
    return JSONResponse(
        {"entry_id": get_review_bookmark(current_user.id)},
        headers={"Cache-Control": "no-store"},
    )


@protected_router.get("/resume_review", response_class=RedirectResponse)
def resume_review(current_user: UserRecord = Depends(require_user)):
    entry_id = get_review_bookmark(current_user.id)
    if not entry_id:
        return RedirectResponse(url="/entries", status_code=303)
    page = db_get_entry_page_number(current_user.id, entry_id) or 1
    return RedirectResponse(
        url=f"/entries?page={page}#{entry_id}", status_code=303
    )


@protected_router.get("/show_synonyms/{entry_id}", response_class=HTMLResponse)
def show_synonyms(
    entry_id: int,
    request: Request,
    current_user: UserRecord = Depends(require_user),
):
    entry = db_get_entry_by_id(current_user.id, entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    _, word = parse_entry_text(entry.text)
    if not word:
        raise HTTPException(status_code=404, detail="Word not valid")
    try:
        senses = get_thesaurus_senses(word)
    except Exception as e:
        logger.error(
            "Error fetching thesaurus senses for %r: %s", word, type(e).__name__
        )
        raise HTTPException(
            status_code=500, detail="Error fetching thesaurus senses"
        )
    context = {
        "entry_id": entry_id,
        "word": word or "",
        "senses": senses,
        "all_words": get_all_words(current_user.id),
    }
    return templates.TemplateResponse(
        request=request, name="synonyms.html.jinja", context=context
    )


@protected_router.get("/inbox", response_class=HTMLResponse)
def inbox_page(
    request: Request,
    current_user: UserRecord = Depends(require_user),
):
    page_notes = db_list_page_notes(current_user.id)
    all_words = get_all_words(current_user.id)
    promoted_count = sum(
        1
        for note in page_notes
        for item in note.items
        if item.promoted_entry_id is not None
    )
    context = {
        "page_notes": page_notes,
        "all_words": all_words,
        "promoted_count": promoted_count,
    }
    return templates.TemplateResponse(
        request=request, name="inbox.html.jinja", context=context
    )


# ---------------------------------------------------------------------------
# Account management (password change + per-device API tokens)
# ---------------------------------------------------------------------------


def _render_account(
    request: Request,
    current_user: UserRecord,
    *,
    password_error: str | None = None,
    password_notice: str | None = None,
    new_token: str | None = None,
    new_token_label: str | None = None,
    status_code: int = 200,
):
    return templates.TemplateResponse(
        request=request,
        name="account.html.jinja",
        context={
            "api_tokens": db_list_api_tokens(current_user.id),
            "password_error": password_error,
            "password_notice": password_notice,
            "new_token": new_token,
            "new_token_label": new_token_label,
        },
        status_code=status_code,
        headers={"Cache-Control": "no-store"},
    )


@protected_router.get("/account", response_class=HTMLResponse)
def account_page(
    request: Request,
    current_user: UserRecord = Depends(require_user),
):
    return _render_account(request, current_user)


@protected_router.post("/account/password", response_class=HTMLResponse)
def change_password(
    request: Request,
    form_data: ChangePasswordForm = Depends(ChangePasswordForm.as_form),
    current_user: UserRecord = Depends(require_user),
):
    verify_csrf_value(request, form_data.csrf_token)
    record = db_get_user_with_password_by_username(current_user.username)
    if not record or not verify_password(form_data.current_password, record[1]):
        return _render_account(
            request,
            current_user,
            password_error="Current password is incorrect.",
            status_code=400,
        )
    if form_data.new_password != form_data.confirm_password:
        return _render_account(
            request,
            current_user,
            password_error="New passwords do not match.",
            status_code=400,
        )
    pw_err = validate_password(form_data.new_password)
    if pw_err:
        return _render_account(
            request,
            current_user,
            password_error=pw_err,
            status_code=400,
        )

    updated = db_update_user_password(
        current_user.id, hash_password(form_data.new_password)
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="User not found")
    # Refresh current session with bumped session_version so other sessions log out.
    start_user_session(request, updated)
    return _render_account(
        request,
        updated,
        password_notice="Password updated. Other sessions have been signed out.",
    )


@protected_router.post("/account/tokens", response_class=HTMLResponse)
def create_api_token(
    request: Request,
    form_data: CreateApiTokenForm = Depends(CreateApiTokenForm.as_form),
    current_user: UserRecord = Depends(require_user),
):
    verify_csrf_value(request, form_data.csrf_token)
    raw_token, digest = generate_opaque_token()
    created = db_create_api_token(current_user.id, form_data.label, digest)
    return _render_account(
        request,
        current_user,
        new_token=raw_token,
        new_token_label=created.label,
    )


@protected_router.post("/account/tokens/{token_id}/revoke")
def revoke_api_token(
    token_id: int,
    _: None = Depends(verify_form_csrf),
    current_user: UserRecord = Depends(require_user),
):
    if not db_revoke_api_token(current_user.id, token_id):
        raise HTTPException(status_code=404, detail="API token not found")
    return RedirectResponse(url="/account", status_code=303)


# ---------------------------------------------------------------------------
# Admin-only routes: filesystem Study Notes (/notes/*) + user/invite admin
# ---------------------------------------------------------------------------


@admin_router.get("/notes/", response_class=HTMLResponse)
def notes(request: Request):
    text = build_directory_tree_markdown(get_notes_dir())
    note_html = markdown2.markdown(
        text,
        extras=["strike", "tables", "toc", "fenced-code-blocks"],
    )
    toc_html = getattr(note_html, "toc_html", "")
    context = {
        "title": "Study Notes",
        "toc_html": toc_html,
        "note_html": note_html,
        "is_dir": True,
        "toc_exist": bool(toc_html),
        "needs_markdown_css": True,
    }
    return templates.TemplateResponse(
        request=request, name="notes.html.jinja", context=context
    )


@admin_router.get("/view_note/{note_path:path}", response_class=HTMLResponse)
def view_note(note_path: str, request: Request) -> _TemplateResponse:
    """Return the rendered HTML of a markdown note by relative path."""
    full_path = safe_path_note(note_path)
    content = full_path.read_text(encoding="utf-8")
    note_html = markdown2.markdown(
        content,
        extras=["strike", "tables", "toc", "fenced-code-blocks"],
    )
    toc_html = getattr(note_html, "toc_html", "")
    context = {
        "title": full_path.name,
        "toc_html": toc_html,
        "note_html": note_html,
        "is_dir": False,
        "toc_exist": bool(toc_html),
        "note_url_path": urllib.parse.quote(note_path, safe="/"),
        "needs_markdown_css": True,
    }
    return templates.TemplateResponse(
        request=request, name="notes.html.jinja", context=context
    )


@admin_router.get("/edit_note/{note_path:path}", response_class=HTMLResponse)
def edit_note_page(note_path: str, request: Request):
    full_path = safe_path_note(note_path)
    content = full_path.read_text(encoding="utf-8")
    context = {
        "note_text": content,
        "note_path": note_path,
        "note_url_path": urllib.parse.quote(note_path, safe="/"),
        "needs_editor": True,
    }
    return templates.TemplateResponse(
        request=request, name="edit_note.html.jinja", context=context
    )


@admin_router.post("/edit_note/{note_path:path}", response_class=HTMLResponse)
def edit_note(
    note_path: str,
    request: Request,
    form_data: EditNoteForm = Depends(EditNoteForm.as_form),
):
    verify_csrf_value(request, form_data.csrf_token)
    full_path = safe_path_note(note_path)
    updated_text = form_data.note_text or ""
    try:
        full_path.write_text(updated_text, encoding="utf-8")
        return RedirectResponse(
            url=f"/view_note/{urllib.parse.quote(note_path, safe='/')}",
            status_code=303,
        )
    except OSError:
        logger.exception("Failed to write note %r", note_path)
        raise HTTPException(status_code=500, detail="Unable to save the note")


def _render_admin(
    request: Request,
    *,
    created_invite_url: str | None = None,
    created_invite_note: str | None = None,
    created_reset_url: str | None = None,
    created_reset_username: str | None = None,
    admin_error: str | None = None,
    status_code: int = 200,
):
    return templates.TemplateResponse(
        request=request,
        name="admin.html.jinja",
        context={
            "users": db_list_users_for_admin(),
            "invites": db_list_invite_tokens(),
            "now_ts": int(time.time()),
            "created_invite_url": created_invite_url,
            "created_invite_note": created_invite_note,
            "created_reset_url": created_reset_url,
            "created_reset_username": created_reset_username,
            "admin_error": admin_error,
        },
        status_code=status_code,
        headers={"Cache-Control": "no-store"},
    )


@admin_router.get("/admin", response_class=HTMLResponse)
def admin_page(request: Request):
    return _render_admin(request)


@admin_router.post("/admin/invites", response_class=HTMLResponse)
def admin_create_invite(
    request: Request,
    form_data: CreateInviteForm = Depends(CreateInviteForm.as_form),
    current_user: UserRecord = Depends(require_admin),
):
    verify_csrf_value(request, form_data.csrf_token)
    raw_code, digest = generate_opaque_token()
    expires_at = int(time.time()) + INVITE_TTL_SECONDS
    invite = db_create_invite_token(
        current_user.id, digest, form_data.note, expires_at
    )
    invite_url = (
        f"{request.url_for('register_page')}?code={urllib.parse.quote(raw_code, safe='')}"
    )
    return _render_admin(
        request,
        created_invite_url=invite_url,
        created_invite_note=invite.note,
    )


@admin_router.post("/admin/invites/{invite_id}/revoke")
def admin_revoke_invite(
    invite_id: int,
    _: None = Depends(verify_form_csrf),
):
    if not db_revoke_invite_token(invite_id):
        raise HTTPException(status_code=404, detail="Invite not found")
    return RedirectResponse(url="/admin", status_code=303)


@admin_router.post("/admin/users/{user_id}/toggle-active", response_class=HTMLResponse)
def admin_toggle_user_active(
    user_id: int,
    request: Request,
    _: None = Depends(verify_form_csrf),
    current_user: UserRecord = Depends(require_admin),
):
    target = db_get_user_by_id(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if target.id == current_user.id:
        return _render_admin(
            request,
            admin_error="You cannot disable your own account.",
            status_code=400,
        )
    if target.is_admin and target.is_active and db_count_active_admins() <= 1:
        return _render_admin(
            request,
            admin_error="Cannot disable the last active admin account.",
            status_code=400,
        )
    db_set_user_active(target.id, not target.is_active)
    return RedirectResponse(url="/admin", status_code=303)


@admin_router.post("/admin/users/{user_id}/reset-link", response_class=HTMLResponse)
def admin_create_reset_link(
    user_id: int,
    request: Request,
    _: None = Depends(verify_form_csrf),
    current_user: UserRecord = Depends(require_admin),
):
    target = db_get_user_by_id(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if not target.is_active:
        return _render_admin(
            request,
            admin_error="Cannot issue a reset link for a disabled account.",
            status_code=400,
        )
    raw_token, digest = generate_opaque_token()
    expires_at = int(time.time()) + PASSWORD_RESET_TTL_SECONDS
    db_create_password_reset_token(target.id, current_user.id, digest, expires_at)
    reset_url = (
        f"{request.url_for('reset_password_page')}"
        f"?token={urllib.parse.quote(raw_token, safe='')}"
    )
    return _render_admin(
        request,
        created_reset_url=reset_url,
        created_reset_username=target.username,
    )


from capture import api_router as capture_api_router  # noqa: E402

app.include_router(protected_router)
app.include_router(admin_router)
app.include_router(capture_api_router)
