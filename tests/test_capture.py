import re

import pytest
from sqlalchemy import create_engine

import auth
import capture
import database
import thesaurus
import utils


pytestmark = pytest.mark.anyio

TEST_API_TOKEN = "test-extension-api-token-at-least-32-chars"


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
            "next_path": "/inbox",
            "csrf_token": csrf_token,
        },
    )
    assert response.status_code == 303


@pytest.fixture
def isolated_db(monkeypatch, tmp_path):
    db_path = tmp_path / "capture.db"
    test_engine = create_engine(
        f"sqlite:///{db_path}",
        future=True,
        connect_args={"check_same_thread": False},
    )
    database.Base.metadata.create_all(test_engine)
    monkeypatch.setattr(database, "engine", test_engine)
    utils.invalidate_words_cache()
    utils.invalidate_quiz_pool_cache()
    thesaurus.fetch_thesaurus_senses.cache_clear()
    try:
        yield test_engine
    finally:
        utils.invalidate_words_cache()
        utils.invalidate_quiz_pool_cache()
        thesaurus.fetch_thesaurus_senses.cache_clear()
        test_engine.dispose()


@pytest.fixture
def configured_api_token(monkeypatch):
    monkeypatch.setenv("DICTIONARY_API_TOKEN", TEST_API_TOKEN)
    auth.get_auth_settings.cache_clear()
    try:
        yield TEST_API_TOKEN
    finally:
        auth.get_auth_settings.cache_clear()


def test_normalize_page_url_variants():
    expected_yt = "https://www.youtube.com/watch?v=VeHFu956WKE"
    assert utils.normalize_page_url("https://youtu.be/VeHFu956WKE?t=2460") == expected_yt
    assert (
        utils.normalize_page_url(
            "https://www.youtube.com/watch?v=VeHFu956WKE&t=2460s&si=abc123"
        )
        == expected_yt
    )
    assert (
        utils.normalize_page_url("https://m.youtube.com/watch?v=VeHFu956WKE#frag")
        == expected_yt
    )
    assert (
        utils.normalize_page_url("https://music.youtube.com/watch?v=VeHFu956WKE")
        == expected_yt
    )
    assert (
        utils.normalize_page_url("https://www.youtube.com/shorts/VeHFu956WKE?feature=share")
        == expected_yt
    )
    assert (
        utils.normalize_page_url("https://www.youtube.com/live/VeHFu956WKE")
        == expected_yt
    )
    assert (
        utils.normalize_page_url("https://www.youtube.com/embed/VeHFu956WKE")
        == expected_yt
    )

    # Non-video YouTube pages stay intact
    assert (
        utils.normalize_page_url("https://www.youtube.com/@somechannel/")
        == "https://www.youtube.com/@somechannel"
    )

    # Tracking params & fragments stripped, query params sorted
    assert (
        utils.normalize_page_url(
            "HTTPS://Example.COM/article/?b=2&utm_source=x&fbclid=1&a=1#section"
        )
        == "https://example.com/article?a=1&b=2"
    )
    assert (
        utils.normalize_page_url("http://localhost:8001/entries/")
        == "http://localhost:8001/entries"
    )

    with pytest.raises(ValueError):
        utils.normalize_page_url("chrome://extensions")
    with pytest.raises(ValueError):
        utils.normalize_page_url("javascript:alert(1)")


async def test_api_auth_bearer_fail_closed_and_session_csrf(
    client, isolated_db, monkeypatch
):
    # Unconfigured api_token rejects bearer even if header is sent
    monkeypatch.delenv("DICTIONARY_API_TOKEN", raising=False)
    monkeypatch.setattr(auth, "load_auth_config", lambda: {})
    auth.get_auth_settings.cache_clear()
    try:
        r_unconf = await client.get(
            "/api/v1/page-note?url=https://example.com/a",
            headers={"Authorization": f"Bearer {TEST_API_TOKEN}"},
        )
        assert r_unconf.status_code == 401
        assert r_unconf.headers.get("www-authenticate") == "Bearer"
    finally:
        auth.get_auth_settings.cache_clear()

    # Configure token
    monkeypatch.setenv("DICTIONARY_API_TOKEN", TEST_API_TOKEN)
    auth.get_auth_settings.cache_clear()
    try:
        # Unauthenticated without header -> 401 JSON
        r_none = await client.get("/api/v1/page-note?url=https://example.com/a")
        assert r_none.status_code == 401
        assert r_none.json()["detail"] == "Authentication required"

        # Valid bearer works
        r_ok = await client.get(
            "/api/v1/page-note?url=https://example.com/a",
            headers={"Authorization": f"Bearer {TEST_API_TOKEN}"},
        )
        assert r_ok.status_code == 200

        # Logged-in session still fails closed if a bad Authorization header is sent
        await _login(client)
        r_bad_bearer = await client.get(
            "/api/v1/page-note?url=https://example.com/a",
            headers={"Authorization": "Bearer wrong-token"},
        )
        assert r_bad_bearer.status_code == 401
        assert r_bad_bearer.headers.get("www-authenticate") == "Bearer"

        # Session without Authorization works on GET, requires CSRF header on PUT
        assert (
            await client.get("/api/v1/page-note?url=https://example.com/a")
        ).status_code == 200
        assert (
            await client.put(
                "/api/v1/page-note",
                json={"url": "https://example.com/a", "notes_md": "hi"},
            )
        ).status_code == 403

        inbox_html = (await client.get("/inbox")).text
        csrf = _csrf_from_html(inbox_html)
        r_put = await client.put(
            "/api/v1/page-note",
            json={"url": "https://example.com/a", "notes_md": "hi"},
            headers={"X-CSRF-Token": csrf},
        )
        assert r_put.status_code == 200

        # Unmatched /api/* route returns JSON 404 (not HTML)
        r_404 = await client.get("/api/v1/nonexistent")
        assert r_404.status_code == 404
        assert "detail" in r_404.json()
    finally:
        auth.get_auth_settings.cache_clear()


async def test_page_note_and_capture_item_lifecycle(
    client, isolated_db, configured_api_token
):
    headers = {"Authorization": f"Bearer {configured_api_token}"}
    yt_short = "https://youtu.be/VeHFu956WKE?t=2460"
    yt_canonical = "https://www.youtube.com/watch?v=VeHFu956WKE"

    # GET on unseen URL is read-only (does not create DB rows)
    r_empty = await client.get(
        f"/api/v1/page-note?url={yt_short}", headers=headers
    )
    assert r_empty.status_code == 200
    assert r_empty.json()["url"] == yt_canonical
    assert r_empty.json()["items"] == []
    assert database.db_list_page_notes() == []

    # Rejects chrome:// URLs
    r_bad = await client.get(
        "/api/v1/page-note?url=chrome://extensions", headers=headers
    )
    assert r_bad.status_code == 400

    # Add captured item with timestamp
    r_add = await client.post(
        "/api/v1/page-note/items",
        json={
            "url": yt_short,
            "title": "Podcast Episode",
            "word": "finances",
            "context": "impact they must have had on their finances",
            "timestamp_seconds": 2460,
        },
        headers=headers,
    )
    assert r_add.status_code == 201
    item_id = r_add.json()["item"]["id"]
    assert r_add.json()["url"] == yt_canonical

    # Save freeform Markdown scratchpad on the same YouTube video via watch URL
    r_put = await client.put(
        "/api/v1/page-note",
        json={
            "url": yt_canonical,
            "title": "Podcast Episode",
            "notes_md": "- plural *finances* = personal money",
        },
        headers=headers,
    )
    assert r_put.status_code == 200
    assert len(r_put.json()["items"]) == 1
    assert r_put.json()["notes_md"] == "- plural *finances* = personal money"

    # Patch item inline
    r_patch = await client.patch(
        f"/api/v1/page-note/items/{item_id}",
        json={"definition_text": "The money a person or organization has."},
        headers=headers,
    )
    assert r_patch.status_code == 200
    assert r_patch.json()["item"]["definition_text"] == (
        "The money a person or organization has."
    )

    # Delete item while notes_md exists -> note stays
    r_del = await client.delete(
        f"/api/v1/page-note/items/{item_id}", headers=headers
    )
    assert r_del.status_code == 200
    assert len(database.db_list_page_notes()) == 1

    # Clearing notes_md with 0 items cleans up the empty PageNote row
    r_clear = await client.put(
        "/api/v1/page-note",
        json={"url": yt_canonical, "title": "Podcast Episode", "notes_md": "   "},
        headers=headers,
    )
    assert r_clear.status_code == 200
    assert r_clear.json()["id"] is None
    assert database.db_list_page_notes() == []


async def test_batch_promote_handles_new_duplicate_invalid_and_idempotent(
    client, isolated_db, configured_api_token
):
    headers = {"Authorization": f"Bearer {configured_api_token}"}
    existing_id = database.db_add_entry("already here - existing")

    def add_item(word, context="", definition=""):
        return client.post(
            "/api/v1/page-note/items",
            json={
                "url": "https://example.com/post",
                "title": "Post",
                "word": word,
                "context": context,
                "definition_text": definition,
            },
            headers=headers,
        )

    i_new = (await add_item("finances", "impact on\ntheir finances", "Money one has.")).json()["item"]["id"]
    i_dup = (await add_item("existing", "already here")).json()["item"]["id"]
    i_bad = (await add_item("bad - word", "ctx")).json()["item"]["id"]

    r_promote = await client.post(
        "/api/v1/page-note/promote",
        json={"item_ids": [i_new, i_dup, i_bad, 999999]},
        headers=headers,
    )
    assert r_promote.status_code == 200
    results = {r["item_id"]: r for r in r_promote.json()["results"]}

    assert results[i_new]["status"] == "created"
    created_entry = database.db_get_entry_by_id(results[i_new]["entry_id"])
    assert created_entry is not None
    assert created_entry.text == "impact on their finances - finances"
    assert len(created_entry.definitions) == 1
    assert created_entry.definitions[0].text == "Money one has."

    assert results[i_dup]["status"] == "duplicate"
    assert results[i_dup]["entry_id"] == existing_id

    assert results[i_bad]["status"] == "error"
    assert results[999999]["status"] == "not_found"

    # Calling promote again on i_new is idempotent
    r_again = await client.post(
        "/api/v1/page-note/promote",
        json={"item_ids": [i_new]},
        headers=headers,
    )
    assert r_again.json()["results"] == [
        {
            "item_id": i_new,
            "status": "already_promoted",
            "entry_id": created_entry.id,
        }
    ]


async def test_lookup_returns_plain_text_and_degrades_gracefully(
    client, isolated_db, configured_api_token, monkeypatch
):
    headers = {"Authorization": f"Bearer {configured_api_token}"}
    eid = database.db_add_entry("impact on their finances - finances")
    monkeypatch.setattr(capture, "get_IPA", lambda w: "fəˈnænsɪz")
    monkeypatch.setattr(
        capture,
        "get_thesaurus_senses_plain",
        lambda w: (
            {
                "part_of_speech": "noun",
                "meaning": "the money a person has",
                "synonyms": ["funds", "resources"],
            },
        ),
    )

    r_ok = await client.get("/api/v1/lookup?word=finances", headers=headers)
    assert r_ok.status_code == 200
    body = r_ok.json()
    assert body["ipa"] == "fəˈnænsɪz"
    assert body["existing_entries"] == [
        {
            "id": eid,
            "word": "finances",
            "context": "impact on their finances",
            "visit_count": 0,
        }
    ]
    assert body["senses"][0]["meaning"] == "the money a person has"
    assert body["thesaurus_error"] is None

    # External thesaurus failure still returns existing_entries and IPA
    def fail_thesaurus(w):
        raise RuntimeError("network down")

    monkeypatch.setattr(capture, "get_thesaurus_senses_plain", fail_thesaurus)
    r_degraded = await client.get("/api/v1/lookup?word=finances", headers=headers)
    assert r_degraded.status_code == 200
    assert r_degraded.json()["existing_entries"][0]["id"] == eid
    assert r_degraded.json()["senses"] == []
    assert r_degraded.json()["thesaurus_error"] is not None


async def test_inbox_page_renders_captured_notes(
    client, isolated_db, configured_api_token
):
    headers = {"Authorization": f"Bearer {configured_api_token}"}
    existing_id = database.db_add_entry("ctx - finances")
    add_fin = await client.post(
        "/api/v1/page-note/items",
        json={
            "url": "https://youtu.be/VeHFu956WKE?t=2460",
            "title": "Podcast Episode",
            "word": "finances",
            "context": "impact on their finances",
            "timestamp_seconds": 2460,
        },
        headers=headers,
    )
    add_new = await client.post(
        "/api/v1/page-note/items",
        json={
            "url": "https://youtu.be/VeHFu956WKE?t=2460",
            "title": "Podcast Episode",
            "word": "ephemeral",
            "context": "an ephemeral trend",
        },
        headers=headers,
    )
    await client.post(
        "/api/v1/page-note/promote",
        json={"item_ids": [add_new.json()["item"]["id"]]},
        headers=headers,
    )

    await _login(client)
    resp = await client.get("/inbox")
    assert resp.status_code == 200
    assert "Podcast Episode" in resp.text
    assert "finances" in resp.text
    assert "41:00" in resp.text
    assert "https://www.google.com/search?q=define%20finances" in resp.text
    assert "https://www.oxfordlearnersdictionaries.com/search/english/?q=finances" in resp.text
    assert "https://www.ldoceonline.com/search/english/direct/?q=finances" in resp.text
    assert "https://www.merriam-webster.com/dictionary/finances" in resp.text
    # Existing dictionary word gets "In dictionary" link, promoted word enables Clear promoted
    assert f'href="/entry/{existing_id}">In dictionary</a>' in resp.text
    assert "Clear promoted (1)" in resp.text
    assert "Delete page" in resp.text
    assert "inbox-edit-form" in resp.text
    assert "inbox-scratchpad-input" in resp.text
    assert add_fin.status_code == 201


async def test_delete_page_note_and_clear_promoted_items(
    client, isolated_db, configured_api_token
):
    headers = {"Authorization": f"Bearer {configured_api_token}"}

    # Note 1: only promoted item, no notes_md -> should be deleted by clear-promoted
    n1_item = (
        await client.post(
            "/api/v1/page-note/items",
            json={"url": "https://example.com/one", "title": "One", "word": "alpha"},
            headers=headers,
        )
    ).json()["item"]["id"]

    # Note 2: one promoted + one unpromoted -> note stays with only unpromoted item
    n2_prom = (
        await client.post(
            "/api/v1/page-note/items",
            json={"url": "https://example.com/two", "title": "Two", "word": "beta"},
            headers=headers,
        )
    ).json()["item"]["id"]
    n2_keep = (
        await client.post(
            "/api/v1/page-note/items",
            json={"url": "https://example.com/two", "title": "Two", "word": "gamma"},
            headers=headers,
        )
    ).json()["item"]["id"]

    # Note 3: only promoted item, HAS notes_md -> note stays with 0 items
    await client.put(
        "/api/v1/page-note",
        json={"url": "https://example.com/three", "title": "Three", "notes_md": "keep me"},
        headers=headers,
    )
    n3_prom = (
        await client.post(
            "/api/v1/page-note/items",
            json={"url": "https://example.com/three", "title": "Three", "word": "delta"},
            headers=headers,
        )
    ).json()["item"]["id"]

    await client.post(
        "/api/v1/page-note/promote",
        json={"item_ids": [n1_item, n2_prom, n3_prom]},
        headers=headers,
    )

    r_clear = await client.post(
        "/api/v1/page-note/clear-promoted", json={}, headers=headers
    )
    assert r_clear.status_code == 200
    assert r_clear.json() == {"deleted": 3}

    remaining = {n.url: n for n in database.db_list_page_notes()}
    assert "https://example.com/one" not in remaining
    assert [i.id for i in remaining["https://example.com/two"].items] == [n2_keep]
    assert remaining["https://example.com/three"].items == []
    assert remaining["https://example.com/three"].notes_md == "keep me"

    # Deleting a page note removes it and its items; deleting again returns 404
    two_id = remaining["https://example.com/two"].id
    r_del = await client.delete(f"/api/v1/page-note/{two_id}", headers=headers)
    assert r_del.status_code == 200
    assert r_del.json() == {"message": "deleted"}
    r_del_again = await client.delete(f"/api/v1/page-note/{two_id}", headers=headers)
    assert r_del_again.status_code == 404
    assert "https://example.com/two" not in {
        n.url for n in database.db_list_page_notes()
    }
