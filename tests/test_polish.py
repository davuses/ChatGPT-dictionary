import logging
import re

import pytest
from sqlalchemy import create_engine

import database
import main
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
            "next_path": "/entries",
            "csrf_token": csrf_token,
        },
    )
    assert response.status_code == 303


@pytest.fixture
def isolated_db(monkeypatch, tmp_path):
    db_path = tmp_path / "polish.db"
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


def test_db_search_escapes_sql_like_wildcards(isolated_db):
    database.db_add_entry("100% effort - percent")
    database.db_add_entry("snake_case name - underscore")
    database.db_add_entry("ordinary phrase - plain")

    pct_entries, pct_total = database.db_get_entries_page(query="100%")
    assert pct_total == 1
    assert pct_entries[0].text == "100% effort - percent"

    under_entries, under_total = database.db_get_entries_page(query="snake_case")
    assert under_total == 1
    assert under_entries[0].text == "snake_case name - underscore"

    only_percent, only_percent_total = database.db_get_entries_page(query="%")
    assert only_percent_total == 1
    assert only_percent[0].text == "100% effort - percent"


def test_get_ipa_is_cached(monkeypatch):
    utils.get_IPA.cache_clear()
    calls = []
    monkeypatch.setattr(
        utils,
        "phonemize",
        lambda word, strip=True, with_stress=True: calls.append(word) or "tɛst",
    )
    try:
        assert utils.get_IPA("cacheword") == "tɛst"
        assert utils.get_IPA("cacheword") == "tɛst"
        assert calls == ["cacheword"]
    finally:
        utils.get_IPA.cache_clear()


def test_get_notes_dir_resolves_relative_to_config_path(monkeypatch, tmp_path):
    config_file = tmp_path / "config.toml"
    config_file.write_text('notes_folder = "my_notes"\nmw_thesaurus_api_key = "k"\n')
    monkeypatch.setattr(utils, "CONFIG_PATH", config_file)
    utils._load_app_config.cache_clear()
    utils.get_notes_dir.cache_clear()
    utils.get_mw_thesaurus_api_key.cache_clear()
    try:
        notes_dir = utils.get_notes_dir()
        assert notes_dir == (tmp_path / "my_notes").resolve()
        assert notes_dir.is_dir()
        assert utils.get_mw_thesaurus_api_key() == "k"
    finally:
        utils._load_app_config.cache_clear()
        utils.get_notes_dir.cache_clear()
        utils.get_mw_thesaurus_api_key.cache_clear()


async def test_show_synonyms_redacts_api_key_in_500_response_and_logs(
    client, isolated_db, monkeypatch, caplog
):
    await _login(client)
    eid = database.db_add_entry("ctx - candid")
    secret_key = "SUPER_SECRET_MW_KEY_12345"

    def boom(word):
        raise RuntimeError(
            f"HTTPSConnectionPool error for https://dictionaryapi.com/?key={secret_key}"
        )

    monkeypatch.setattr(main, "get_thesaurus_senses", boom)
    with caplog.at_level(logging.ERROR):
        resp = await client.get(f"/show_synonyms/{eid}")

    assert resp.status_code == 500
    assert "Error fetching thesaurus senses" in resp.text
    assert secret_key not in resp.text
    assert secret_key not in caplog.text


async def test_delete_entry_and_definition_return_404_json_when_missing(
    client, isolated_db
):
    await _login(client)
    csrf_token = _csrf_from_html((await client.get("/add_entry")).text)
    headers = {"X-CSRF-Token": csrf_token}

    missing_entry = await client.delete("/delete_entry/999999", headers=headers)
    assert missing_entry.status_code == 404
    assert missing_entry.json() == {"detail": "Entry not found"}

    missing_def = await client.delete("/delete_definition/999999", headers=headers)
    assert missing_def.status_code == 404
    assert missing_def.json() == {"detail": "Definition not found"}

    eid = database.db_add_entry("ctx - ephemeral", definition_text="short-lived")
    def_id = database.db_get_entry_by_id(eid).definitions[0].id

    del_def = await client.delete(f"/delete_definition/{def_id}", headers=headers)
    assert del_def.status_code == 200
    assert del_def.json() == {"message": "deleted"}

    del_entry = await client.delete(f"/delete_entry/{eid}", headers=headers)
    assert del_entry.status_code == 200
    assert del_entry.json() == {"message": "deleted"}


async def test_entry_page_encodes_audio_urls_cleanly(client, isolated_db, monkeypatch):
    await _login(client)
    eid = database.db_add_entry("ctx - Pipe dream/wish")
    monkeypatch.setattr(main, "get_IPA", lambda w: "paɪp driːm")

    resp = await client.get(f"/entry/{eid}")
    assert resp.status_code == 200
    assert (
        'src="https://ssl.gstatic.com/dictionary/static/sounds/oxford/'
        'pipe%20dream%2Fwish--_us_1.mp3"' in resp.text
    )
    assert (
        'src="https://www.google.com/speech-api/v1/synthesize?'
        'text=Pipe+dream%2Fwish&enc=mpeg' in resp.text
    )


async def test_edit_note_oserror_returns_500_page(
    client, monkeypatch, tmp_path
):
    await _login(client)
    csrf_token = _csrf_from_html((await client.get("/add_entry")).text)
    note_file = tmp_path / "sample.md"
    note_file.write_text("# Hello", encoding="utf-8")

    monkeypatch.setattr(main, "safe_path_note", lambda _: note_file)

    def fail_write(self, *args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(type(note_file), "write_text", fail_write)

    resp = await client.post(
        "/edit_note/sample.md",
        data={"note_text": "updated", "csrf_token": csrf_token},
    )
    assert resp.status_code == 500
    assert "Unable to save the note" in resp.text
