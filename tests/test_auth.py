import re

import pytest

import main
from auth import safe_next_path


pytestmark = pytest.mark.anyio


def _csrf_from_html(html: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert match
    return match.group(1)


async def _login(client):
    login_page = await client.get("/login?next=/add_entry")
    assert login_page.status_code == 200
    csrf_token = _csrf_from_html(login_page.text)
    response = await client.post(
        "/login",
        data={
            "username": "test-admin",
            "password": "correct horse battery staple",
            "next_path": "/add_entry",
            "csrf_token": csrf_token,
        },
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/add_entry"
    cookie = response.headers["set-cookie"].lower()
    assert "secure" in cookie
    assert "httponly" in cookie
    assert "samesite=lax" in cookie


async def test_public_editor_redirects_to_login(client):
    response = await client.get("/add_entry")
    assert response.status_code == 303
    assert response.headers["location"] == "/login?next=%2Fadd_entry"
    login_page = await client.get("/login")
    assert "Admin login" in login_page.text


async def test_notes_are_private(client):
    response = await client.get("/notes/")
    assert response.status_code == 303
    assert response.headers["location"] == "/login?next=%2Fnotes%2F"


async def test_unauthenticated_mutation_is_rejected(client):
    response = await client.post(
        "/add_entry",
        data={"entry_text": "must not exist", "csrf_token": "invalid"},
    )
    assert response.status_code == 401


async def test_login_rejects_bad_credentials_without_creating_admin_session(client):
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
    assert (await client.get("/add_entry")).status_code == 303


async def test_authenticated_editor_has_csrf_and_logout_requires_it(client):
    await _login(client)
    editor = await client.get("/add_entry")
    assert editor.status_code == 200
    assert "Log out" in editor.text
    assert "Signed in as admin" in editor.text
    assert 'href="/login"' not in editor.text
    csrf_token = _csrf_from_html(editor.text)

    assert (await client.post("/logout")).status_code == 403
    logout = await client.post("/logout", data={"csrf_token": csrf_token})
    assert logout.status_code == 303
    assert (await client.get("/add_entry")).status_code == 303


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


def test_anonymous_quiz_does_not_update_visit_tracking(monkeypatch):
    question = main.QuizQuestion(1, "word", "A _____ in context")
    monkeypatch.setattr(main, "pick_random_question", lambda **_: question)
    visits = []
    monkeypatch.setattr(
        main, "db_entry_last_visit_old_enough", lambda entry_id: visits.append(entry_id)
    )
    monkeypatch.setattr(
        main, "db_entry_increment_visit_count", lambda entry_id: visits.append(entry_id)
    )

    returned, _ = main._next_quiz_question("", track_visit=False)
    assert returned == question
    assert visits == []


async def test_api_documentation_is_disabled(client):
    assert (await client.get("/docs")).status_code == 404
    assert (await client.get("/openapi.json")).status_code == 404


def test_next_redirect_must_stay_on_this_site():
    assert safe_next_path("/entry/1?q=test") == "/entry/1?q=test"
    assert safe_next_path("https://attacker.example/") == "/"
    assert safe_next_path("//attacker.example/") == "/"
    assert safe_next_path("///attacker.example/") == "/"
    assert safe_next_path("/\\attacker.example/") == "/"
    assert safe_next_path("/entry/1\r\nLocation: https://attacker.example") == "/"
