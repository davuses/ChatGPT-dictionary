import os
import re
import secrets
import threading
import time
import tomllib
from collections import deque
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import Form, HTTPException, Request
from pwdlib import PasswordHash

from database import (
    UserRecord,
    db_get_user_by_api_token_hash,
    db_get_user_by_id,
    db_get_user_with_password_by_username,
    hash_token,
)

SESSION_USER_ID_KEY = "user_id"
SESSION_VERSION_KEY = "session_version"
SESSION_CSRF_KEY = "csrf_token"
SESSION_MAX_AGE = 30 * 24 * 60 * 60
AUTH_CONFIG_PATH = Path(__file__).with_name("config.toml")

MIN_PASSWORD_LENGTH = 10
MAX_PASSWORD_LENGTH = 128
_USERNAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{1,31}$")

password_hash = PasswordHash.recommended()
# Precomputed valid Argon2id hash used to equalize timing when a login targets
# a nonexistent username (prevents timing-based username enumeration).
_DUMMY_PASSWORD_HASH = (
    "$argon2id$v=19$m=65536,t=3,p=4$4sOvaQHchgzGdiRLpiaQQA$"
    "Ce21Qdouf1AflTvk6wEk9LZQdIcxSDf9jCvQANpi2f4"
)

_UNSET = object()


@dataclass(frozen=True)
class AuthSettings:
    username: str
    password_hash: str
    session_secret: str
    https_only: bool
    api_token: str = ""


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
    api_token = os.environ.get(
        "DICTIONARY_API_TOKEN", _auth_text(auth_config, "api_token")
    ).strip()

    config_https_only = auth_config.get("https_only", True)
    if not isinstance(config_https_only, bool):
        raise RuntimeError("auth.https_only in config.toml must be true or false")
    https_only_value = os.environ.get(
        "DICTIONARY_HTTPS_ONLY", str(config_https_only)
    ).lower()

    if not session_secret:
        raise RuntimeError("Missing required authentication setting: session_secret")
    if len(session_secret) < 32:
        raise RuntimeError("The session secret must be at least 32 characters")
    if api_token and len(api_token) < 32:
        raise RuntimeError("The API token must be at least 32 characters")
    if https_only_value not in {"true", "false"}:
        raise RuntimeError("DICTIONARY_HTTPS_ONLY must be 'true' or 'false'")

    return AuthSettings(
        username=username,
        password_hash=admin_password_hash,
        session_secret=session_secret,
        https_only=https_only_value == "true",
        api_token=api_token,
    )


def validate_username(raw_username: str) -> tuple[str | None, str | None]:
    cleaned = raw_username.strip()
    if not _USERNAME_RE.match(cleaned):
        return (
            None,
            "Username must be 2–32 characters, start with a letter or number, "
            "and use only letters, numbers, '.', '_', or '-'.",
        )
    return cleaned, None


def validate_password(password: str) -> str | None:
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"Password must be at least {MIN_PASSWORD_LENGTH} characters."
    if len(password) > MAX_PASSWORD_LENGTH:
        return f"Password must be at most {MAX_PASSWORD_LENGTH} characters."
    return None


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, stored_hash: str) -> bool:
    if len(password) > MAX_PASSWORD_LENGTH:
        return False
    try:
        return password_hash.verify(password, stored_hash)
    except (TypeError, ValueError):
        return False


def authenticate(username: str, password: str) -> UserRecord | None:
    if len(password) > MAX_PASSWORD_LENGTH:
        return None
    clean_username = username.strip()
    if not clean_username:
        verify_password(password, _DUMMY_PASSWORD_HASH)
        return None

    record = db_get_user_with_password_by_username(clean_username)
    if record is None:
        # Equalize timing so attackers cannot distinguish valid vs unknown usernames.
        verify_password(password, _DUMMY_PASSWORD_HASH)
        return None

    user, stored_hash = record
    if not verify_password(password, stored_hash):
        return None
    if not user.is_active:
        return None
    return user


def generate_opaque_token() -> tuple[str, str]:
    """Generate a high-entropy URL-safe token (>= 32 chars) and its SHA-256 hex digest."""
    raw = secrets.token_urlsafe(32)
    return raw, hash_token(raw)


def get_csrf_token(request: Request) -> str:
    token = request.session.get(SESSION_CSRF_KEY)
    if not isinstance(token, str) or not token:
        token = secrets.token_urlsafe(32)
        request.session[SESSION_CSRF_KEY] = token
    return token


def start_user_session(request: Request, user: UserRecord) -> None:
    request.session.clear()
    request.session[SESSION_USER_ID_KEY] = user.id
    request.session[SESSION_VERSION_KEY] = user.session_version
    request.session[SESSION_CSRF_KEY] = secrets.token_urlsafe(32)
    request.state._current_user = user


def end_user_session(request: Request) -> None:
    request.session.clear()
    request.state._current_user = None


def get_current_user(request: Request) -> UserRecord | None:
    cached = getattr(request.state, "_current_user", _UNSET)
    if cached is not _UNSET:
        return cached

    user_id = request.session.get(SESSION_USER_ID_KEY)
    session_version = request.session.get(SESSION_VERSION_KEY)
    user: UserRecord | None = None
    if isinstance(user_id, int) and isinstance(session_version, int):
        candidate = db_get_user_by_id(user_id)
        if (
            candidate is not None
            and candidate.is_active
            and candidate.session_version == session_version
        ):
            user = candidate

    request.state._current_user = user
    return user


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


async def require_user(request: Request) -> UserRecord:
    user = get_current_user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user


async def require_admin(request: Request) -> UserRecord:
    user = await require_user(request)
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


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


async def require_api_user(request: Request) -> UserRecord:
    """Authenticate /api/v1/* via per-user Bearer token (Chrome extension) or
    existing browser session + X-CSRF-Token on state-changing methods.

    Fail-closed: if an Authorization header is present, never fall back to
    session cookies and reject revoked tokens or disabled users.
    """
    auth_header = request.headers.get("authorization")
    if auth_header is not None:
        scheme, sep, raw_token = auth_header.partition(" ")
        token = raw_token.strip()
        if scheme.lower() != "bearer" or not sep or not token:
            raise HTTPException(
                status_code=401,
                detail="Invalid API token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        user = db_get_user_by_api_token_hash(hash_token(token))
        if user is None or not user.is_active:
            raise HTTPException(
                status_code=401,
                detail="Invalid API token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        request.state._current_user = user
        return user

    user = get_current_user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        verify_csrf_value(request, request.headers.get("X-CSRF-Token"))
    return user


def auth_template_context(request: Request) -> dict[str, object]:
    user = get_current_user(request)
    return {
        "is_authenticated": user is not None,
        "is_admin": bool(user and user.is_admin),
        "current_user": user,
        "csrf_token": get_csrf_token(request) if user is not None else None,
    }


# ---------------------------------------------------------------------------
# Bounded in-memory sliding-window rate limiter for auth endpoints
# ---------------------------------------------------------------------------


class SlidingWindowLimiter:
    def __init__(self, *, window_seconds: int = 300, max_keys: int = 2048) -> None:
        self._window = window_seconds
        self._max_keys = max_keys
        self._lock = threading.Lock()
        self._buckets: dict[str, deque[float]] = {}

    def _prune_key(self, dq: deque[float], cutoff: float) -> None:
        while dq and dq[0] <= cutoff:
            dq.popleft()

    def is_limited(self, key: str, limit: int, *, now: float | None = None) -> bool:
        ts = time.monotonic() if now is None else now
        cutoff = ts - self._window
        with self._lock:
            dq = self._buckets.get(key)
            if not dq:
                return False
            self._prune_key(dq, cutoff)
            if not dq:
                self._buckets.pop(key, None)
                return False
            return len(dq) >= limit

    def record(self, key: str, *, now: float | None = None) -> None:
        ts = time.monotonic() if now is None else now
        cutoff = ts - self._window
        with self._lock:
            if len(self._buckets) >= self._max_keys and key not in self._buckets:
                # Prune expired keys; if still full, drop oldest key.
                expired = [
                    k
                    for k, dq in self._buckets.items()
                    if not dq or dq[-1] <= cutoff
                ]
                for k in expired:
                    self._buckets.pop(k, None)
                if len(self._buckets) >= self._max_keys:
                    oldest_key = next(iter(self._buckets))
                    self._buckets.pop(oldest_key, None)

            dq = self._buckets.setdefault(key, deque())
            self._prune_key(dq, cutoff)
            dq.append(ts)

    def clear_key(self, key: str) -> None:
        with self._lock:
            self._buckets.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._buckets.clear()


_auth_rate_limiter = SlidingWindowLimiter(window_seconds=300, max_keys=2048)
_PER_SUBJECT_LIMIT = 10
_PER_IP_LIMIT = 40


def _client_ip(request: Request) -> str:
    return request.client.host if request.client and request.client.host else "unknown"


def check_auth_rate_limit(
    request: Request, action: str, subject: str = ""
) -> bool:
    """Return True if the caller has exceeded the rate limit for `action`."""
    ip = _client_ip(request)
    if _auth_rate_limiter.is_limited(f"{action}:ip:{ip}", _PER_IP_LIMIT):
        return True
    if subject:
        norm = subject.strip().lower()
        if _auth_rate_limiter.is_limited(
            f"{action}:subj:{ip}:{norm}", _PER_SUBJECT_LIMIT
        ):
            return True
    return False


def record_auth_failure(
    request: Request, action: str, subject: str = ""
) -> None:
    ip = _client_ip(request)
    _auth_rate_limiter.record(f"{action}:ip:{ip}")
    if subject:
        norm = subject.strip().lower()
        _auth_rate_limiter.record(f"{action}:subj:{ip}:{norm}")


def clear_auth_failures(
    request: Request, action: str, subject: str = ""
) -> None:
    if subject:
        ip = _client_ip(request)
        _auth_rate_limiter.clear_key(f"{action}:subj:{ip}:{subject.strip().lower()}")


def clear_all_rate_limits() -> None:
    _auth_rate_limiter.clear()
