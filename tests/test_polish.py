import logging
import re

import pytest
from sqlalchemy import create_engine

import database
import main
import thesaurus
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


def test_db_search_escapes_sql_like_wildcards(admin_user):
    database.db_add_entry(admin_user.id, "100% effort - percent")
    database.db_add_entry(admin_user.id, "snake_case name - underscore")
    database.db_add_entry(admin_user.id, "ordinary phrase - plain")

    pct_entries, pct_total = database.db_get_entries_page(admin_user.id, query="100%")
    assert pct_total == 1
    assert pct_entries[0].text == "100% effort - percent"

    under_entries, under_total = database.db_get_entries_page(admin_user.id, query="snake_case")
    assert under_total == 1
    assert under_entries[0].text == "snake_case name - underscore"

    only_percent, only_percent_total = database.db_get_entries_page(admin_user.id, query="%")
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
    client, admin_user, monkeypatch, caplog
):
    await _login(client)
    eid = database.db_add_entry(admin_user.id, "ctx - candid")
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
    client, admin_user
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

    eid = database.db_add_entry(admin_user.id, "ctx - ephemeral", definition_text="short-lived")
    def_id = database.db_get_entry_by_id(admin_user.id, eid).definitions[0].id

    del_def = await client.delete(f"/delete_definition/{def_id}", headers=headers)
    assert del_def.status_code == 200
    assert del_def.json() == {"message": "deleted"}

    del_entry = await client.delete(f"/delete_entry/{eid}", headers=headers)
    assert del_entry.status_code == 200
    assert del_entry.json() == {"message": "deleted"}


async def test_entry_page_encodes_audio_urls_cleanly(client, admin_user, monkeypatch):
    await _login(client)
    eid = database.db_add_entry(admin_user.id, "ctx - Pipe dream/wish")
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


def test_get_how_long_ago_formatting():
    now = 1_750_000_000
    assert utils.get_how_long_ago(None, now=now) == "never"
    assert utils.get_how_long_ago(now - 20, now=now) == "just now"
    assert utils.get_how_long_ago(now - 300, now=now) == "5 min ago"
    assert utils.get_how_long_ago(now - 3600, now=now) == "1 hour ago"
    assert utils.get_how_long_ago(now - 5 * 3600, now=now) == "5 hours ago"
    assert utils.get_how_long_ago(now - 86400, now=now) == "1 day ago"
    assert utils.get_how_long_ago(now - 45 * 86400, now=now) == "1 month 15 days ago"
    assert utils.get_how_long_ago(now - 430 * 86400, now=now) == "1 year 2 months ago"


async def test_entry_page_ui_polish_and_offline_audio(
    client, admin_user, monkeypatch
):
    await _login(client)
    eid = database.db_add_entry(admin_user.id, "She spoke with candor - candor")
    monkeypatch.setattr(main, "get_IPA", lambda w: "ˈkændər")

    # Newly created entry has visit_count=0 -> simulate 1 visit
    database.db_record_entry_visit(admin_user.id, eid, now=int(2_000_000_000))
    resp = await client.get(f"/entry/{eid}")
    assert resp.status_code == 200
    assert "fonts.googleapis.com" not in resp.text
    assert 'class="audio-btn"' in resp.text
    assert "1 visit</span>" in resp.text
    assert "<h2>Context</h2>" in resp.text
    assert "She spoke with candor" in resp.text
    assert 'data-entry-text="She spoke with candor - candor"' in resp.text
    assert 'class="page-narrow"' in resp.text


async def test_dashboard_quick_search_and_entries_visit_tiers(
    client, admin_user
):
    await _login(client)
    e0 = database.db_add_entry(admin_user.id, "ctx zero - zero")
    e5 = database.db_add_entry(admin_user.id, "ctx five - five")
    base_ts = 2_000_000_000
    for step in range(5):
        database.db_record_entry_visit(
            admin_user.id,
            e5,
            now=base_ts + step * (database.VISIT_COOLDOWN_SECONDS + 1),
        )

    dash = await client.get("/")
    assert dash.status_code == 200
    assert 'class="page-narrow"' in dash.text
    assert 'action="/entries"' in dash.text

    entries = await client.get("/entries")
    assert entries.status_code == 200
    assert "visit-0" in entries.text
    assert "visit-high" in entries.text
    assert 'class="back-to-top"' in entries.text
    assert "unselectable" not in entries.text


async def test_synonyms_handles_sim_list_stems_phrases_and_escaping(
    client, admin_user, monkeypatch
):
    thesaurus.fetch_thesaurus_senses.cache_clear()
    await _login(client)
    e_phrase = database.db_add_entry(admin_user.id, "ctx - zero in on")
    e_linked = database.db_add_entry(admin_user.id, "ctx - Focus")

    mw_payload = [
        {
            "meta": {
                "id": "zero (in on)",
                "stems": ["zero (in on)", "zero in on"],
                "syns": [["focus", "concentrate"]],
            },
            "hwi": {"hw": "zero (in on)"},
            "fl": "verb",
            "shortdef": ["to direct one's attention to"],
            "def": [
                {
                    "sseq": [
                        [
                            [
                                "sense",
                                {
                                    "dt": [
                                        [
                                            "text",
                                            "to direct <script>alert(1)</script> attention to",
                                        ]
                                    ],
                                    "sim_list": [[{"wd": "focus"}, {"wd": "concentrate"}]],
                                },
                            ]
                        ]
                    ]
                }
            ],
        }
    ]

    calls = []

    class FakeResp:
        status_code = 200

        def json(self):
            return mw_payload

    def fake_get(url, timeout):
        calls.append(url)
        return FakeResp()

    monkeypatch.setattr(thesaurus.requests, "get", fake_get)
    monkeypatch.setattr(utils, "get_mw_thesaurus_api_key", lambda: "fake-key")

    try:
        resp = await client.get(f"/show_synonyms/{e_phrase}")
        assert resp.status_code == 200
        assert "concentrate" in resp.text
        assert f'/entry/{e_linked}">focus</a>' in resp.text
        # Meaning from MW must be autoescaped, never rendered | safe
        assert "<script>alert(1)</script>" not in resp.text
        assert "&lt;script&gt;alert(1)&lt;/script&gt;" in resp.text

        # Case-insensitive cache hit: "Zero In On" reuses cached "zero in on"
        senses_again = utils.get_thesaurus_senses("  Zero   In On ")
        assert len(senses_again) == 1
        assert len(calls) == 1
    finally:
        thesaurus.fetch_thesaurus_senses.cache_clear()


def test_thesaurus_errors_raise_and_do_not_poison_cache(monkeypatch):
    thesaurus.fetch_thesaurus_senses.cache_clear()
    attempts = {"n": 0}

    class FakeOkResp:
        status_code = 200

        def json(self):
            return [
                {
                    "meta": {"id": "candid", "stems": ["candid"], "syns": [["frank"]]},
                    "hwi": {"hw": "candid"},
                    "fl": "adjective",
                    "shortdef": ["honest and direct"],
                    "def": [],
                }
            ]

    def flaky_get(url, timeout):
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise thesaurus.requests.Timeout("timed out")
        if attempts["n"] == 2:
            resp = FakeOkResp()
            resp.status_code = 503
            return resp
        return FakeOkResp()

    monkeypatch.setattr(thesaurus.requests, "get", flaky_get)
    try:
        with pytest.raises(thesaurus.ThesaurusError):
            thesaurus.lookup_thesaurus("candid", "secret-key")
        with pytest.raises(thesaurus.ThesaurusError):
            thesaurus.lookup_thesaurus("candid", "secret-key")

        # Subsequent call succeeds because failures were not cached
        senses = thesaurus.lookup_thesaurus("Candid", "secret-key")
        assert len(senses) == 1
        assert senses[0].synonyms == ("frank",)
        assert attempts["n"] == 3
    finally:
        thesaurus.fetch_thesaurus_senses.cache_clear()


def test_highlight_ipa_preserves_escaped_html_and_wraps_ipa():
    raw = "<p>Use &lt;script&gt;alert(1)&lt;/script&gt; with /ˈkændər/ safely.</p>"
    result = utils.highlight_ipa(raw)
    assert "<script>" not in result
    assert "&lt;script&gt;" in result
    assert '<span class="ipa">/ˈkændər/</span>' in result


async def test_notes_special_chars_and_entries_edge_cases(
    client, admin_user, monkeypatch, tmp_path
):
    await _login(client)
    note_file = tmp_path / "C# 100% notes.md"
    note_file.write_text("# Notes", encoding="utf-8")
    monkeypatch.setattr(utils, "get_notes_dir", lambda: tmp_path)

    view_resp = await client.get("/view_note/C%23%20100%25%20notes.md")
    assert view_resp.status_code == 200
    assert "/edit_note/C%23%20100%25%20notes.md" in view_resp.text

    # Page clamping + empty search state
    database.db_add_entry(admin_user.id, "ctx - alpha")
    clamped = await client.get("/entries?page=999")
    assert clamped.status_code == 200
    assert "alpha" in clamped.text

    empty_search = await client.get("/entries?q=zzznomatch")
    assert empty_search.status_code == 200
    assert "No matching entries" in empty_search.text

    # Blank definition rejected with 400
    csrf_token = _csrf_from_html((await client.get("/add_entry")).text)
    eid = database.db_add_entry(admin_user.id, "ctx - beta")
    blank_def = await client.post(
        "/add_definition",
        data={"entry_id": eid, "definition_text": "   ", "csrf_token": csrf_token},
    )
    assert blank_def.status_code == 400



async def test_static_assets_include_content_hash_for_cache_busting(client):
    style_url = main.static_url("style.css")
    script_url = main.static_url("script.js")
    assert style_url.startswith("/static/style.css?v=")
    assert len(style_url.split("?v=")[1]) == 12
    assert script_url.startswith("/static/script.js?v=")
    assert main.static_url("nonexistent.css") == "/static/nonexistent.css"

    login_page = await client.get("/login")
    assert login_page.status_code == 200
    assert f'href="{style_url}"' in login_page.text
    assert f'src="{script_url}"' in login_page.text



