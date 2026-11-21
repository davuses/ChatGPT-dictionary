import os
import secrets
import tomllib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import Depends, Form, HTTPException, Request
from pwdlib import PasswordHash


SESSION_AUTH_KEY = "admin_authenticated"
SESSION_CSRF_KEY = "csrf_token"
SESSION_MAX_AGE = 30 * 24 * 60 * 60
AUTH_CONFIG_PATH = Path(__file__).with_name("config.toml")

password_hash = PasswordHash.recommended()


@dataclass(frozen=True)
class AuthSettings:
    username: str
    password_hash: str
    session_secret: str
    https_only: bool


def load_auth_config() -> dict[str, object]:
    """Load the optional [auth] section from the local, gitignored config."""
    try:
        with AUTH_CONFIG_PATH.open("rb") as config_file:
            config = tomllib.load(config_file)
    except FileNotFoundError:
        return {}
    except tomllib.TOMLDecodeError as error:
        raise RuntimeError("config.toml contains invalid TOML") from error

    auth_config = config.get("auth", {})
    if not isinstance(auth_config, dict):
        raise RuntimeError("[auth] in config.toml must be a table")
    return auth_config


def _auth_text(auth_config: dict[str, object], name: str) -> str:
    value = auth_config.get(name, "")
    if not isinstance(value, str):
        raise RuntimeError(f"auth.{name} in config.toml must be a string")
    return value.strip()


@lru_cache
def get_auth_settings() -> AuthSettings:
    auth_config = load_auth_config()
    username = os.environ.get(
        "DICTIONARY_ADMIN_USERNAME", _auth_text(auth_config, "admin_username")
    ).strip()
    admin_password_hash = os.environ.get(
        "DICTIONARY_ADMIN_PASSWORD_HASH",
        _auth_text(auth_config, "admin_password_hash"),
    ).strip()
    session_secret = os.environ.get(
        "DICTIONARY_SESSION_SECRET", _auth_text(auth_config, "session_secret")
    )

    config_https_only = auth_config.get("https_only", True)
    if not isinstance(config_https_only, bool):
        raise RuntimeError("auth.https_only in config.toml must be true or false")
    https_only_value = os.environ.get(
        "DICTIONARY_HTTPS_ONLY", str(config_https_only)
    ).lower()

    missing = [
        name
        for name, value in (
            ("admin_username", username),
            ("admin_password_hash", admin_password_hash),
            ("session_secret", session_secret),
        )
        if not value
    ]
    if missing:
        raise RuntimeError(
            "Missing required authentication settings: "
            + ", ".join(missing)
        )
    if len(session_secret) < 32:
        raise RuntimeError("The session secret must be at least 32 characters")
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
        raise RuntimeError("Configured admin password hash is not valid")
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


async def verify_header_csrf(request: Request) -> None:
    verify_csrf_value(request, request.headers.get("X-CSRF-Token"))


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
