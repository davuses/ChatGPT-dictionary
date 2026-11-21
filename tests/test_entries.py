import re

import pytest
from sqlalchemy import create_engine

import database
import utils


pytestmark = pytest.mark.anyio


def _csrf_from_html(html: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert match
    return match.group(1)


async def _login(client):
    login_page = await client.get("/login")
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


@pytest.fixture
def isolated_db(monkeypatch, tmp_path):
    db_path = tmp_path / "test.db"
    test_engine = create_engine(
        f"sqlite:///{db_path}",
        future=True,
        connect_args={"check_same_thread": False},
    )
    database.Base.metadata.create_all(test_engine)
    monkeypatch.setattr(database, "engine", test_engine)
    utils.invalidate_words_cache()
    utils.invalidate_quiz_pool_cache()
    try:
        yield test_engine
    finally:
        utils.invalidate_words_cache()
        utils.invalidate_quiz_pool_cache()
        test_engine.dispose()


def test_parse_and_format_entry_text():
    assert utils.parse_entry_text("She spoke - softly - terse") == (
        "She spoke - softly",
        "terse",
    )
    assert utils.parse_entry_text("  ubiquitous  ") == ("", "ubiquitous")
    assert utils.format_entry_text("terse", "She spoke - softly") == (
        "She spoke - softly - terse"
    )
    assert utils.format_entry_text("  ubiquitous ", "   ") == "ubiquitous"


def test_bare_word_with_example_is_quizzable_without_blanking_whole_sentence(
    isolated_db,
):
    e1 = database.db_add_entry(
        "ephemeral",
        example_text="> Fame in the digital age is often ephemeral and fleeting.",
    )
    # Multi-word phrase whose example is almost just the phrase itself must be skipped
    database.db_add_entry(
        "take for granted",
        example_text="> We take for granted.",
    )

    pool = utils.get_quiz_pool()
    assert [c.entry_id for c in pool] == [e1]
    assert pool[0].word == "ephemeral"


async def test_one_step_add_entry_creates_entry_definition_and_example(
    client, isolated_db
):
    await _login(client)
    add_page = await client.get("/add_entry")
    assert add_page.status_code == 200
    assert "md-editor.min.js" not in add_page.text
    csrf_token = _csrf_from_html(add_page.text)

    response = await client.post(
        "/add_entry",
        data={
            "word": "candor",
            "context": "Her candor disarmed the whole room.",
            "definition_text": "Open, honest, and frank expression.",
            "example_text": "> I appreciate your candor on this matter.",
            "csrf_token": csrf_token,
        },
    )
    assert response.status_code == 303
    entry_id = int(response.headers["location"].rsplit("/", 1)[-1])

    saved = database.db_get_entry_by_id(entry_id)
    assert saved is not None
    assert saved.text == "Her candor disarmed the whole room. - candor"
    assert len(saved.definitions) == 1
    assert saved.definitions[0].text == "Open, honest, and frank expression."
    assert saved.example == "> I appreciate your candor on this matter."


async def test_add_entry_skips_blank_definition_and_example(client, isolated_db):
    await _login(client)
    csrf_token = _csrf_from_html((await client.get("/add_entry")).text)

    response = await client.post(
        "/add_entry",
        data={
            "word": "laconic",
            "context": "",
            "definition_text": "   ",
            "example_text": "  \n ",
            "csrf_token": csrf_token,
        },
    )
    assert response.status_code == 303
    entry_id = int(response.headers["location"].rsplit("/", 1)[-1])
    saved = database.db_get_entry_by_id(entry_id)
    assert saved is not None
    assert saved.text == "laconic"
    assert saved.definitions == []
    assert saved.example is None


async def test_add_entry_inline_400_and_409_preserve_draft(client, isolated_db):
    await _login(client)
    csrf_token = _csrf_from_html((await client.get("/add_entry")).text)

    empty_resp = await client.post(
        "/add_entry",
        data={
            "word": "   ",
            "context": "Draft context",
            "definition_text": "Draft def",
            "example_text": "Draft ex",
            "csrf_token": csrf_token,
        },
    )
    assert empty_resp.status_code == 400
    assert "Word cannot be empty." in empty_resp.text
    assert "Draft context" in empty_resp.text
    assert "Draft def" in empty_resp.text
    assert "Draft ex" in empty_resp.text

    sep_resp = await client.post(
        "/add_entry",
        data={
            "word": "foo - bar",
            "context": "Some context",
            "csrf_token": csrf_token,
        },
    )
    assert sep_resp.status_code == 400
    assert "reserved as the context separator" in sep_resp.text
    assert "foo - bar" in sep_resp.text

    existing_id = database.db_add_entry("Some context - vivid")
    dup_resp = await client.post(
        "/add_entry",
        data={
            "word": "vivid",
            "context": "Some context",
            "definition_text": "Keep my typed draft",
            "csrf_token": csrf_token,
        },
    )
    assert dup_resp.status_code == 409
    assert "already exists" in dup_resp.text
    assert f'href="/entry/{existing_id}"' in dup_resp.text
    assert "Keep my typed draft" in dup_resp.text


async def test_edit_entry_splits_fields_handles_duplicates_and_404s(
    client, isolated_db
):
    await _login(client)
    e1 = database.db_add_entry("First - part - alpha")
    e2 = database.db_add_entry("Second context - beta")

    edit_page = await client.get(f"/edit_entry/{e1}")
    assert edit_page.status_code == 200
    assert "md-editor.min.js" not in edit_page.text
    assert 'value="alpha"' in edit_page.text
    assert 'value="First - part"' in edit_page.text
    csrf_token = _csrf_from_html(edit_page.text)

    dup = await client.post(
        f"/edit_entry/{e1}",
        data={"word": "beta", "context": "Second context", "csrf_token": csrf_token},
    )
    assert dup.status_code == 409
    assert f'href="/entry/{e2}"' in dup.text

    updated = await client.post(
        f"/edit_entry/{e1}",
        data={"word": "gamma", "context": "Updated context", "csrf_token": csrf_token},
    )
    assert updated.status_code == 303
    assert updated.headers["location"] == f"/entry/{e1}"
    assert database.db_get_entry_by_id(e1).text == "Updated context - gamma"

    missing_entry = await client.post(
        "/edit_entry/999999",
        data={"word": "ghost", "context": "", "csrf_token": csrf_token},
    )
    assert missing_entry.status_code == 404

    missing_def = await client.post(
        "/edit_definition/999999",
        data={"definition_text": "x", "csrf_token": csrf_token},
    )
    assert missing_def.status_code == 404

    missing_ex = await client.post(
        "/edit_example/999999",
        data={"example_text": "x", "csrf_token": csrf_token},
    )
    assert missing_ex.status_code == 404
