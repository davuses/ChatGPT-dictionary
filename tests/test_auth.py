import re

import pytest
from fastapi.routing import APIRoute

import auth
import main
from auth import safe_next_path


pytestmark = pytest.mark.anyio


def _csrf_from_html(html: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert match
    return match.group(1)


async def _login(client, next_path: str = "/add_entry"):
    login_page = await client.get(f"/login?next={next_path}")
    assert login_page.status_code == 200
    csrf_token = _csrf_from_html(login_page.text)
    response = await client.post(
        "/login",
        data={
            "username": "test-admin",
            "password": "correct horse battery staple",
            "next_path": next_path,
            "csrf_token": csrf_token,
        },
    )
    assert response.status_code == 303
    assert response.headers["location"] == next_path
    cookie = response.headers["set-cookie"].lower()
    assert "secure" in cookie
    assert "httponly" in cookie
    assert "samesite=lax" in cookie


def test_all_non_login_routes_require_authentication():
    public_routes = {("GET", "/login"), ("POST", "/login")}
    for route in main.app.routes:
        if not isinstance(route, APIRoute):
            continue
        dep_calls = {dep.call for dep in route.dependant.dependencies}
        for method in route.methods:
            if (method, route.path) in public_routes:
                assert auth.require_admin not in dep_calls
            else:
                assert auth.require_admin in dep_calls, (
                    f"Route {method} {route.path} is missing require_admin"
                )


@pytest.mark.parametrize(
    ("path", "expected_next"),
    [
        ("/", "%2F"),
        ("/entries", "%2Fentries"),
        ("/entries?q=hello", "%2Fentries%3Fq%3Dhello"),
        ("/entry/1", "%2Fentry%2F1"),
        ("/show_synonyms/1", "%2Fshow_synonyms%2F1"),
        ("/add_entry", "%2Fadd_entry"),
        ("/resume_review", "%2Fresume_review"),
        ("/notes/", "%2Fnotes%2F"),
    ],
)
async def test_unauthenticated_pages_redirect_to_login(client, path, expected_next):
    response = await client.get(path)
    assert response.status_code == 303
    assert response.headers["location"] == f"/login?next={expected_next}"


async def test_login_page_and_static_assets_stay_public(client):
    login_page = await client.get("/login")
    assert login_page.status_code == 200
    assert "Log in" in login_page.text
    assert "Admin login" not in login_page.text
    assert 'href="/entries"' not in login_page.text

    css = await client.get("/static/style.css")
    assert css.status_code == 200


async def test_unauthenticated_json_and_xhr_requests_return_401_json(client):
    for path, headers in (
        ("/quiz/next", {}),
        ("/review_bookmark", {}),
        ("/entries?q=test", {"X-Requested-With": "XMLHttpRequest"}),
        ("/entries?q=test", {"Accept": "application/json"}),
        ("/entries", {"Sec-Fetch-Mode": "cors"}),
    ):
        response = await client.get(path, headers=headers)
        assert response.status_code == 401
        assert response.json() == {"detail": "Authentication required"}


async def test_unauthenticated_mutation_is_rejected_before_form_validation(client):
    response = await client.post(
        "/add_entry",
        data={"entry_text": "must not exist", "csrf_token": "invalid"},
    )
    assert response.status_code == 401
    assert response.json() == {"detail": "Authentication required"}

    malformed = await client.post("/add_entry", data={})
    assert malformed.status_code == 401
    assert malformed.json() == {"detail": "Authentication required"}


async def test_login_rejects_bad_credentials_without_creating_session(client):
    login_page = await client.get("/login")
    csrf_token = _csrf_from_html(login_page.text)
    response = await client.post(
        "/login",
        data={
            "username": "test-admin",
            "password": "wrong",
            "next_path": "/",
            "csrf_token": csrf_token,
        },
    )
    assert response.status_code == 401
    assert "Invalid username or password" in response.text
    assert (await client.get("/")).status_code == 303


async def test_authenticated_editor_has_csrf_and_logout_redirects_to_login(client):
    await _login(client)
    editor = await client.get("/add_entry")
    assert editor.status_code == 200
    assert "Log out" in editor.text
    assert "Signed in as admin" not in editor.text
    assert 'href="/login"' not in editor.text
    csrf_token = _csrf_from_html(editor.text)

    assert (await client.post("/logout")).status_code == 403
    logout = await client.post("/logout", data={"csrf_token": csrf_token})
    assert logout.status_code == 303
    assert logout.headers["location"] == "/login"
    assert (await client.get("/")).status_code == 303


async def test_authenticated_notes_uses_study_notes_title(client, monkeypatch):
    await _login(client, next_path="/notes/")
    monkeypatch.setattr(main, "build_directory_tree_markdown", lambda _: "- [Demo](/view_note/demo.md)")
    response = await client.get("/notes/")
    assert response.status_code == 200
    assert "<title>Study Notes</title>" in response.text
    assert "IELTS Notes" not in response.text


async def test_authenticated_javascript_mutation_requires_csrf_header(client):
    await _login(client)
    editor = await client.get("/add_entry")
    csrf_token = _csrf_from_html(editor.text)

    assert (await client.post("/entry/999999/set_review_bookmark")).status_code == 403
    response = await client.post(
        "/entry/999999/set_review_bookmark",
        headers={"X-CSRF-Token": csrf_token},
    )
    assert response.status_code == 404


async def test_authenticated_form_mutation_requires_csrf(client, monkeypatch):
    await _login(client)
    calls = []
    monkeypatch.setattr(main, "db_add_entry", lambda text: calls.append(text) or 123)

    rejected = await client.post(
        "/add_entry",
        data={"entry_text": "test entry", "csrf_token": "invalid"},
    )
    assert rejected.status_code == 403
    assert calls == []

    editor = await client.get("/add_entry")
    accepted = await client.post(
        "/add_entry",
        data={
            "entry_text": "test entry",
            "csrf_token": _csrf_from_html(editor.text),
        },
    )
    assert accepted.status_code == 303
    assert accepted.headers["location"] == "/entry/123"
    assert calls == ["test entry"]


async def test_api_documentation_is_disabled(client):
    assert (await client.get("/docs")).status_code == 404
    assert (await client.get("/openapi.json")).status_code == 404


def test_session_max_age_is_30_days():
    assert auth.SESSION_MAX_AGE == 30 * 24 * 60 * 60


def test_next_redirect_must_stay_on_this_site():
    assert safe_next_path("/entry/1?q=test") == "/entry/1?q=test"
    assert safe_next_path("https://attacker.example/") == "/"
    assert safe_next_path("//attacker.example/") == "/"
    assert safe_next_path("///attacker.example/") == "/"
    assert safe_next_path("/\\attacker.example/") == "/"
    assert safe_next_path("/entry/1\r\nLocation: https://attacker.example") == "/"


def test_auth_settings_can_come_from_toml(monkeypatch, tmp_path):
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """[auth]
admin_username = "toml-admin"
admin_password_hash = "$argon2id$test-hash"
session_secret = "toml-session-secret-at-least-32-chars"
https_only = false
"""
    )
    monkeypatch.setattr(auth, "AUTH_CONFIG_PATH", config_path)
    for variable in (
        "DICTIONARY_ADMIN_USERNAME",
        "DICTIONARY_ADMIN_PASSWORD_HASH",
        "DICTIONARY_SESSION_SECRET",
        "DICTIONARY_HTTPS_ONLY",
    ):
        monkeypatch.delenv(variable, raising=False)
    auth.get_auth_settings.cache_clear()
    try:
        settings = auth.get_auth_settings()
        assert settings.username == "toml-admin"
        assert settings.password_hash == "$argon2id$test-hash"
        assert settings.session_secret == "toml-session-secret-at-least-32-chars"
        assert settings.https_only is False
    finally:
        auth.get_auth_settings.cache_clear()


def test_environment_overrides_toml_auth_settings(monkeypatch):
    monkeypatch.setattr(
        auth,
        "load_auth_config",
        lambda: {
            "admin_username": "toml-admin",
            "admin_password_hash": "toml-hash",
            "session_secret": "toml-session-secret-at-least-32-chars",
            "https_only": True,
        },
    )
    monkeypatch.setenv("DICTIONARY_ADMIN_USERNAME", "environment-admin")
    monkeypatch.setenv("DICTIONARY_HTTPS_ONLY", "false")
    monkeypatch.delenv("DICTIONARY_ADMIN_PASSWORD_HASH", raising=False)
    monkeypatch.delenv("DICTIONARY_SESSION_SECRET", raising=False)
    auth.get_auth_settings.cache_clear()
    try:
        settings = auth.get_auth_settings()
        assert settings.username == "environment-admin"
        assert settings.password_hash == "toml-hash"
        assert settings.https_only is False
    finally:
        auth.get_auth_settings.cache_clear()
