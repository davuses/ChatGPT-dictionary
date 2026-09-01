import os
import secrets
from dataclasses import dataclass
from functools import lru_cache
from urllib.parse import urlsplit

from fastapi import Depends, Form, HTTPException, Request
from pwdlib import PasswordHash


SESSION_AUTH_KEY = "admin_authenticated"
SESSION_CSRF_KEY = "csrf_token"
SESSION_MAX_AGE = 8 * 60 * 60

password_hash = PasswordHash.recommended()


@dataclass(frozen=True)
class AuthSettings:
    username: str
    password_hash: str
    session_secret: str
    https_only: bool


@lru_cache
def get_auth_settings() -> AuthSettings:
    username = os.environ.get("DICTIONARY_ADMIN_USERNAME", "").strip()
    admin_password_hash = os.environ.get(
        "DICTIONARY_ADMIN_PASSWORD_HASH", ""
    ).strip()
    session_secret = os.environ.get("DICTIONARY_SESSION_SECRET", "")
    https_only_value = os.environ.get("DICTIONARY_HTTPS_ONLY", "true").lower()

    missing = [
        name
        for name, value in (
            ("DICTIONARY_ADMIN_USERNAME", username),
            ("DICTIONARY_ADMIN_PASSWORD_HASH", admin_password_hash),
            ("DICTIONARY_SESSION_SECRET", session_secret),
        )
        if not value
    ]
    if missing:
        raise RuntimeError(
            "Missing required authentication environment variables: "
            + ", ".join(missing)
        )
    if len(session_secret) < 32:
        raise RuntimeError("DICTIONARY_SESSION_SECRET must be at least 32 characters")
    if https_only_value not in {"true", "false"}:
        raise RuntimeError("DICTIONARY_HTTPS_ONLY must be 'true' or 'false'")

    return AuthSettings(
        username,
        admin_password_hash,
        session_secret,
        https_only=https_only_value == "true",
    )


def is_admin(request: Request) -> bool:
    return request.session.get(SESSION_AUTH_KEY) is True


def get_csrf_token(request: Request) -> str:
    token = request.session.get(SESSION_CSRF_KEY)
    if not isinstance(token, str) or not token:
        token = secrets.token_urlsafe(32)
        request.session[SESSION_CSRF_KEY] = token
    return token


def authenticate(username: str, password: str) -> bool:
    settings = get_auth_settings()
    username_matches = secrets.compare_digest(username, settings.username)
    try:
        password_matches = password_hash.verify(password, settings.password_hash)
    except (TypeError, ValueError):
        raise RuntimeError("DICTIONARY_ADMIN_PASSWORD_HASH is not a valid hash")
    return username_matches and password_matches


def start_admin_session(request: Request) -> None:
    request.session.clear()
    request.session[SESSION_AUTH_KEY] = True
    request.session[SESSION_CSRF_KEY] = secrets.token_urlsafe(32)


def end_admin_session(request: Request) -> None:
    request.session.clear()


def safe_next_path(candidate: str | None, default: str = "/") -> str:
    if not candidate:
        return default
    if candidate.startswith("//") or "\\" in candidate:
        return default
    if any(ord(character) < 32 for character in candidate):
        return default
    parsed = urlsplit(candidate)
    if parsed.scheme or parsed.netloc or not candidate.startswith("/"):
        return default
    return candidate


async def require_admin(request: Request) -> None:
    if not is_admin(request):
        raise HTTPException(status_code=401, detail="Authentication required")


def verify_csrf_value(request: Request, submitted: str | None) -> None:
    expected = request.session.get(SESSION_CSRF_KEY)
    if (
        not isinstance(expected, str)
        or not isinstance(submitted, str)
        or not secrets.compare_digest(expected, submitted)
    ):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")


async def verify_form_csrf(
    request: Request, csrf_token: str | None = Form(None)
) -> None:
    verify_csrf_value(request, csrf_token)


async def require_admin_with_form_csrf(
    request: Request,
    _: None = Depends(require_admin),
    csrf_token: str | None = Form(None),
) -> None:
    verify_csrf_value(request, csrf_token)


async def require_admin_with_header_csrf(
    request: Request, _: None = Depends(require_admin)
) -> None:
    verify_csrf_value(request, request.headers.get("X-CSRF-Token"))


def auth_template_context(request: Request) -> dict[str, object]:
    authenticated = is_admin(request)
    return {
        "is_authenticated": authenticated,
        "csrf_token": get_csrf_token(request) if authenticated else None,
    }
