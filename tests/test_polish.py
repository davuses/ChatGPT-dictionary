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


def test_get_ipa_batch_single_call_and_error_fallback(monkeypatch):
    utils.get_IPA.cache_clear()
    batch_calls = []

    def fake_phonemize(words, strip=True, with_stress=True):
        batch_calls.append(words)
        if isinstance(words, list):
            return ["hˈʌŋkɚ dˈaʊn", "mˈaɪlɪdʒ"][: len(words)]
        return "hˈʌŋkɚ dˈaʊn"

    monkeypatch.setattr(utils, "phonemize", fake_phonemize)
    try:
        first = utils.get_IPA_batch(["hunker down", "mileage", "hunker down", ""])
        assert first == {"hunker down": "hˈʌŋkɚ dˈaʊn", "mileage": "mˈaɪlɪdʒ"}
        assert batch_calls == [["hunker down", "mileage"]]

        # Cached entries hit memory without calling phonemize again
        assert utils.get_IPA("mileage") == "mˈaɪlɪdʒ"
        assert utils.get_IPA_batch(["mileage"]) == {"mileage": "mˈaɪlɪdʒ"}
        assert len(batch_calls) == 1

        # Failures degrade to "" without crashing or poisoning the cache
        monkeypatch.setattr(
            utils,
            "phonemize",
            lambda *_a, **_kw: (_ for _ in ()).throw(RuntimeError("espeak missing")),
        )
        assert utils.get_IPA_batch(["unseen"]) == {"unseen": ""}
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
    assert 'id="entry-audio-btn"' in resp.text
    assert 'data-word="Pipe dream/wish"' in resp.text
    assert "merriam-webster.com/dictionary/Pipe%20dream" in resp.text
    assert "google.com/search?q=define%20Pipe%20dream" in resp.text


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


def test_strip_markdown_to_plain():
    raw = (
        "### Meaning\r\n"
        "> **To skimp** means to spend *too little* [money](https://example.com).\r\n\r\n"
        "- Avoid `poor` ~~quality~~\r\n"
        "- Be overly frugal\r\n"
    )
    plain = utils.strip_markdown_to_plain(raw)
    assert "**" not in plain
    assert "###" not in plain
    assert "https://example.com" not in plain
    assert "To skimp means to spend too little money." in plain
    assert "• Avoid poor quality" in plain
    assert "• Be overly frugal" in plain


async def test_definitions_tab_renders_clamped_plain_definitions_and_xhr(
    client, admin_user
):
    short_id = database.db_add_entry(
        admin_user.id,
        "She remained steadfast - steadfast",
        "Firm and unwavering.",
    )
    long_def = (
        "**To skimp** means to spend too little money, time, or effort on something, "
        "often in a way that results in poor quality or inadequate coverage. "
        "It suggests being overly frugal or neglecting necessary details. <script>alert(1)</script>"
    )
    long_id = database.db_add_entry(
        admin_user.id,
        "Never skimp on brakes - skimp",
        long_def,
    )
    empty_id = database.db_add_entry(
        admin_user.id,
        "A brand new idiom - brand new",
        "",
    )
    utils.invalidate_words_cache(admin_user.id)

    await _login(client)

    resp = await client.get("/entries?show_definition=true")
    assert resp.status_code == 200
    assert "entries-table--definitions" in resp.text
    assert 'id="tab-definitions"' in resp.text
    assert "Firm and unwavering." in resp.text
    assert "To skimp means to spend too little money" in resp.text
    assert "**To skimp**" not in resp.text
    assert "<script>alert(1)</script>" not in resp.text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in resp.text
    assert 'class="definition-toggle"' in resp.text
    assert f'href="/add_definition?entry_id={empty_id}"' in resp.text
    assert f'id="{short_id}"' in resp.text
    assert f'id="{long_id}"' in resp.text

    # XHR live search preserves definitions mode and highlights matching text
    xhr = await client.get(
        "/entries?show_definition=true&q=skimp",
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert xhr.status_code == 200
    payload = xhr.json()
    assert payload["count"] == 1
    assert "entries-table--definitions" in payload["results_html"]
    assert "<mark>skimp</mark>" in payload["results_html"]


async def test_entries_sorting_and_definition_search(client, admin_user):
    e1 = database.db_add_entry(admin_user.id, "ctx - alpha", "unique_gloss_needle")
    e2 = database.db_add_entry(admin_user.id, "ctx - beta", "other meaning")
    e3 = database.db_add_entry(admin_user.id, "ctx - gamma", "")
    base_ts = int(database.time.time()) + database.VISIT_COOLDOWN_SECONDS + 10
    for step in range(3):
        database.db_record_entry_visit(
            admin_user.id, e1, now=base_ts + step * (database.VISIT_COOLDOWN_SECONDS + 1)
        )
    database.db_record_entry_visit(admin_user.id, e2, now=base_ts)

    await _login(client)

    r_newest = await client.get("/entries?sort=newest")
    assert r_newest.status_code == 200
    assert r_newest.text.index(f'id="{e3}"') < r_newest.text.index(f'id="{e2}"') < r_newest.text.index(f'id="{e1}"')

    r_unvisited = await client.get("/entries?sort=unvisited")
    assert r_unvisited.status_code == 200
    assert r_unvisited.text.index(f'id="{e3}"') < r_unvisited.text.index(f'id="{e2}"') < r_unvisited.text.index(f'id="{e1}"')

    r_most = await client.get("/entries?sort=most_visited")
    assert r_most.status_code == 200
    assert r_most.text.index(f'id="{e1}"') < r_most.text.index(f'id="{e2}"') < r_most.text.index(f'id="{e3}"')

    # Definition text is searched only in show_definition mode
    r_all = await client.get("/entries?q=unique_gloss_needle")
    assert f'id="{e1}"' not in r_all.text
    r_def = await client.get("/entries?show_definition=true&q=unique_gloss_needle")
    assert f'id="{e1}"' in r_def.text
    assert "<mark>unique_gloss_needle</mark>" in r_def.text


async def test_quick_search_ranking_and_user_isolation(client, admin_user):
    other = database.db_create_user("other-member", "x" * 60, is_admin=False)
    e_ctx = database.db_add_entry(admin_user.id, "She saw a starlight sky - twilight")
    e_mid = database.db_add_entry(admin_user.id, "ctx - outsmart")
    e_pre = database.db_add_entry(admin_user.id, "ctx - stark")
    database.db_add_entry(other.id, "ctx - starship")

    await _login(client)
    resp = await client.get("/api/v1/quick-search?q=star")
    assert resp.status_code == 200
    items = resp.json()["items"]
    words = [item["word"] for item in items]
    assert "starship" not in words
    assert [item["id"] for item in items] == [e_pre, e_ctx]
    assert e_mid not in [item["id"] for item in items]


async def test_nav_inbox_badge_dashboard_pills_and_rich_quiz_next(client, admin_user):
    e1 = database.db_add_entry(
        admin_user.id,
        "The team showed great candor during the meeting - candor",
        "**Frankness** and honesty in expression.",
    )
    e2 = database.db_add_entry(admin_user.id, "ctx - undefinedword", "")
    database.db_set_review_bookmark(admin_user.id, e1)
    database.db_add_capture_item(
        admin_user.id,
        "https://example.com/article",
        "Example Article",
        word="ephemeral",
        context="Trends are ephemeral.",
    )
    utils.invalidate_quiz_pool_cache(admin_user.id)

    await _login(client)
    dash = await client.get("/")
    assert dash.status_code == 200
    assert 'id="nav-inbox-badge">1<' in dash.text
    assert "1 inbox item waiting" in dash.text
    assert "1 word needs definition" in dash.text
    assert "Last marked: candor" in dash.text
    assert 'id="quick-search-dialog"' in dash.text

    q_resp = await client.get("/quiz/next")
    assert q_resp.status_code == 200
    q_data = q_resp.json()
    assert q_data["entry_id"] == e1
    assert q_data["headword"] == "candor"
    assert q_data["sentence_matches"] == ["candor"]
    assert len(q_data["sentence_parts"]) == 2
    assert "Frankness and honesty in expression." in q_data["definition_preview"]
    assert e2 != e1


async def test_phase3_entry_detail_lookup_synonym_links_review_and_admin(
    client, admin_user, monkeypatch
):
    e1 = database.db_add_entry(
        admin_user.id,
        "She spoke with candor at the forum. - candor",
        "```text\nfrankness\n```\n\n| a | b |\n|---|---|\n| 1 | 2 |",
    )
    e2 = database.db_add_entry(admin_user.id, "ctx - frankness")
    utils.invalidate_words_cache(admin_user.id)
    utils.invalidate_quiz_pool_cache(admin_user.id)

    await _login(client)

    entry_resp = await client.get(f"/entry/{e1}")
    assert entry_resp.status_code == 200
    assert 'id="entry-audio-btn"' in entry_resp.text
    assert "<audio " not in entry_resp.text
    assert "merriam-webster.com/dictionary/candor" in entry_resp.text
    assert 'id="inline-entry-form"' in entry_resp.text
    assert 'id="inline-def-form"' in entry_resp.text
    assert 'id="inline-example-form"' in entry_resp.text
    assert 'id="entry-synonyms-details"' in entry_resp.text
    assert 'id="entry-shortcuts-dialog"' in entry_resp.text
    assert "navigator.clipboard" in entry_resp.text
    assert "readText" not in entry_resp.text
    assert "<table>" in entry_resp.text
    assert "<pre>" in entry_resp.text

    # /api/v1/lookup with include_synonym_links=true
    monkeypatch.setattr(
        "capture.get_thesaurus_senses_plain",
        lambda _w: ({"part_of_speech": "noun", "meaning": "honesty", "synonyms": ["frankness", "openness"]},),
    )
    lookup_resp = await client.get("/api/v1/lookup?word=candor&include_synonym_links=true")
    assert lookup_resp.status_code == 200
    lookup_data = lookup_resp.json()
    assert lookup_data["synonym_links"] == {"frankness": e2}

    # /review accepts size=30 and renders Again/Got it + audio button
    review_resp = await client.get("/review?size=30")
    assert review_resp.status_code == 200
    assert 'id="review-again-btn"' in review_resp.text
    assert 'id="review-audio-btn"' in review_resp.text
    assert "/review?size=30" in review_resp.text

    # /admin renders confirmation attributes on destructive actions
    database.db_create_user("alice", "x" * 60, is_admin=False)
    database.db_create_invite_token(admin_user.id, "hash-inv-1", "Alice", int(database.time.time()) + 3600)
    admin_resp = await client.get("/admin")
    assert admin_resp.status_code == 200
    assert 'data-confirm-key="confirm_revoke_invite"' in admin_resp.text
    assert 'data-confirm-key="confirm_disable_user"' in admin_resp.text


async def test_phase4_cm6_preview_and_inbox_note_deleted(client, admin_user):
    # Unauthenticated preview is rejected
    assert (await client.post("/markdown/preview", json={"text": "**hi**"})).status_code == 401

    e1 = database.db_add_entry(admin_user.id, "ctx - candor")
    await _login(client)

    add_def = await client.get(f"/add_definition?entry_id={e1}")
    assert add_def.status_code == 200
    assert "cm6-editor.js" in add_def.text
    assert "md-editor.min.js" not in add_def.text
    assert "font-awesome.min.css" not in add_def.text

    csrf_token = _csrf_from_html(add_def.text)
    assert (await client.post("/markdown/preview", json={"text": "**hi**"})).status_code == 403

    preview = await client.post(
        "/markdown/preview",
        json={"text": "**bold** /ˈkændər/ <script>alert(1)</script>\n\n```py\nx=1\n```"},
        headers={"X-CSRF-Token": csrf_token},
    )
    assert preview.status_code == 200
    assert preview.headers.get("cache-control") == "no-store"
    html = preview.json()["html"]
    assert "<strong>bold</strong>" in html
    assert '<span class="ipa">/ˈkændər/</span>' in html
    assert "<script>" not in html
    assert "<pre>" in html

    # Inbox DELETE returns note_deleted accurately
    _, item1 = database.db_add_capture_item(
        admin_user.id, "https://example.com/p1", "Page 1", word="alpha"
    )
    _, item2 = database.db_add_capture_item(
        admin_user.id, "https://example.com/p1", "Page 1", word="beta"
    )
    inbox = await client.get("/inbox")
    assert inbox.status_code == 200
    assert "inbox-collapse-btn" in inbox.text
    assert "inbox-lookup-toggle" in inbox.text

    del1 = await client.delete(
        f"/api/v1/page-note/items/{item1.id}", headers={"X-CSRF-Token": csrf_token}
    )
    assert del1.status_code == 200
    assert del1.json() == {"message": "deleted", "note_deleted": False}

    del2 = await client.delete(
        f"/api/v1/page-note/items/{item2.id}", headers={"X-CSRF-Token": csrf_token}
    )
    assert del2.status_code == 200
    assert del2.json() == {"message": "deleted", "note_deleted": True}


async def test_extension_visibility_update_guide_and_version_parity(client, admin_user):
    import json
    from pathlib import Path

    manifest = json.loads(
        (Path(__file__).resolve().parent.parent / "extension" / "manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest["version"] == utils.EXTENSION_VERSION

    await _login(client)

    dash = await client.get("/")
    assert dash.status_code == 200
    assert ">Chrome extension<" in dash.text
    assert 'href="/account#extension"' in dash.text

    account = await client.get("/account")
    assert account.status_code == 200
    assert "Chrome Side Panel Extension" in account.text
    assert "Alt+Shift+D" in account.text
    assert "Updating an existing install?" in account.text
    assert "do not click Remove" in account.text

    note_resp = await client.get("/api/v1/page-note?url=https://example.com/vercheck")
    assert note_resp.status_code == 200
    assert note_resp.json()["latest_extension_version"] == utils.EXTENSION_VERSION








