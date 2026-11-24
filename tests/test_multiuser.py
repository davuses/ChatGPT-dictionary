import re
import sqlite3

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine

import auth
import database
import main


pytestmark = pytest.mark.anyio


def _csrf_from_html(html: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert match
    return match.group(1)


def _new_client() -> AsyncClient:
    return AsyncClient(
        transport=ASGITransport(app=main.app),
        base_url="https://dictionary.test",
        follow_redirects=False,
    )


async def _login_as(client: AsyncClient, username: str, password: str) -> None:
    page = await client.get("/login")
    csrf = _csrf_from_html(page.text)
    resp = await client.post(
        "/login",
        data={
            "username": username,
            "password": password,
            "next_path": "/",
            "csrf_token": csrf,
        },
    )
    assert resp.status_code == 303


def test_legacy_single_user_migration_preserves_data_and_fks(monkeypatch, tmp_path):
    legacy_db = tmp_path / "legacy.db"
    conn = sqlite3.connect(str(legacy_db))
    conn.executescript(
        """
        PRAGMA journal_mode = WAL;
        PRAGMA foreign_keys = ON;
        CREATE TABLE question (
            id INTEGER NOT NULL PRIMARY KEY,
            text VARCHAR NOT NULL UNIQUE,
            is_hidden BOOLEAN DEFAULT 0,
            example VARCHAR,
            visit_count INTEGER DEFAULT 0,
            last_visit INTEGER,
            last_review INTEGER
        );
        CREATE TABLE "answer" (
            id INTEGER NOT NULL PRIMARY KEY,
            text VARCHAR NOT NULL,
            question_id INTEGER NOT NULL REFERENCES question(id) ON DELETE CASCADE
        );
        CREATE TABLE global_state (
            id INTEGER PRIMARY KEY,
            last_review_question_id INTEGER REFERENCES question(id) ON DELETE SET NULL
        );
        CREATE TABLE page_note (
            id INTEGER NOT NULL PRIMARY KEY,
            url VARCHAR NOT NULL,
            title VARCHAR NOT NULL,
            notes_md VARCHAR NOT NULL,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL
        );
        CREATE UNIQUE INDEX ix_page_note_url ON page_note (url);
        CREATE TABLE page_capture_item (
            id INTEGER NOT NULL PRIMARY KEY,
            page_note_id INTEGER NOT NULL REFERENCES page_note(id) ON DELETE CASCADE,
            word VARCHAR NOT NULL,
            context VARCHAR NOT NULL,
            definition_text VARCHAR NOT NULL,
            timestamp_seconds INTEGER,
            promoted_entry_id INTEGER REFERENCES question(id) ON DELETE SET NULL,
            created_at INTEGER NOT NULL
        );

        INSERT INTO question (id, text, example, visit_count, last_visit)
        VALUES (10, 'She spoke with candor - candor', '> Her candor helped.', 3, 1700000000);
        INSERT INTO answer (id, text, question_id)
        VALUES (20, 'Honesty and directness.', 10);
        INSERT INTO global_state (id, last_review_question_id) VALUES (1, 10);
        INSERT INTO page_note (id, url, title, notes_md, created_at, updated_at)
        VALUES (30, 'https://example.com/post', 'Post', 'notes here', 1700000000, 1700000000);
        INSERT INTO page_capture_item (id, page_note_id, word, context, definition_text, timestamp_seconds, promoted_entry_id, created_at)
        VALUES (40, 30, 'candor', 'She spoke with candor', 'Honesty', 120, 10, 1700000000);
        """
    )
    conn.close()

    eng = create_engine(
        f"sqlite:///{legacy_db}",
        future=True,
        connect_args={"check_same_thread": False},
    )
    monkeypatch.setattr(database, "engine", eng)
    legacy_token = "legacy-extension-token-at-least-32-chars"
    try:
        admin = database.bootstrap_database(
            admin_username="owner",
            admin_password_hash=auth.hash_password("owner-super-secret"),
            legacy_api_token=legacy_token,
            target_engine=eng,
        )
        assert admin is not None
        assert admin.username == "owner"
        assert admin.is_admin is True
        assert admin.last_review_question_id == 10

        # WAL-safe backup file exists
        backups = list(tmp_path.glob("legacy.db.bak-*"))
        assert len(backups) == 1

        # Foreign keys intact and user_version bumped
        verify_conn = sqlite3.connect(str(legacy_db))
        assert verify_conn.execute("PRAGMA user_version").fetchone()[0] == 1
        assert verify_conn.execute("PRAGMA foreign_key_check").fetchall() == []
        verify_conn.close()

        # Existing entries, definitions, page notes, and capture items preserved
        migrated_entry = database.db_get_entry_by_id(admin.id, 10)
        assert migrated_entry is not None
        assert len(migrated_entry.definitions) == 1
        assert migrated_entry.definitions[0].id == 20

        migrated_note = database.db_get_page_note_by_url(
            admin.id, "https://example.com/post"
        )
        assert migrated_note is not None
        assert len(migrated_note.items) == 1
        assert migrated_note.items[0].id == 40
        assert migrated_note.items[0].promoted_entry_id == 10

        # Legacy API token migrated to api_token table
        tok_user = database.db_get_user_by_api_token_hash(
            database.hash_token(legacy_token)
        )
        assert tok_user is not None and tok_user.id == admin.id

        # Second user can save identical entry text & page URL without UNIQUE collision
        friend = database.db_create_user("alice", auth.hash_password("alice-secret-pw"))
        friend_eid = database.db_add_entry(
            friend.id, "She spoke with candor - candor", definition_text="Alice def"
        )
        assert friend_eid != 10
        friend_note = database.db_upsert_page_note(
            friend.id, "https://example.com/post", "Post", "alice notes"
        )
        assert friend_note is not None and friend_note.id != 30

        # Re-running bootstrap is idempotent and creates no extra backups
        database.bootstrap_database(
            admin_username="owner",
            admin_password_hash="ignored",
            legacy_api_token="ignored-token-at-least-32-characters",
            target_engine=eng,
        )
        assert len(list(tmp_path.glob("legacy.db.bak-*"))) == 1
    finally:
        eng.dispose()


async def test_invite_registration_single_use_and_admin_only_guards(client):
    await _login_as(client, "test-admin", "correct horse battery staple")
    admin_resp = await client.get("/admin")
    assert admin_resp.status_code == 200
    csrf = _csrf_from_html(admin_resp.text)

    inv_resp = await client.post(
        "/admin/invites",
        data={"note": "Alice", "csrf_token": csrf},
    )
    assert inv_resp.status_code == 200
    assert inv_resp.headers.get("cache-control") == "no-store"
    match = re.search(r'id="created-invite-url" value="([^"]+)"', inv_resp.text)
    assert match
    invite_url = match.group(1)
    code = invite_url.split("code=", 1)[1]

    async with _new_client() as alice_client:
        reg_page = await alice_client.get(f"/register?code={code}")
        assert reg_page.status_code == 200
        assert reg_page.headers.get("referrer-policy") == "no-referrer"
        assert reg_page.headers.get("cache-control") == "no-store"
        reg_csrf = _csrf_from_html(reg_page.text)

        reg_post = await alice_client.post(
            "/register",
            data={
                "code": code,
                "username": "alice",
                "password": "alice-strong-password",
                "confirm_password": "alice-strong-password",
                "csrf_token": reg_csrf,
            },
        )
        assert reg_post.status_code == 303
        assert reg_post.headers["location"] == "/"

        # Alice's dashboard hides Notes and Admin links
        dash = await alice_client.get("/")
        assert dash.status_code == 200
        assert 'href="/notes/"' not in dash.text
        assert 'href="/admin"' not in dash.text
        assert 'href="/account"' in dash.text

        # Non-admin gets styled 403 on /notes/* and /admin
        for forbidden_path in ("/notes/", "/view_note/demo.md", "/edit_note/demo.md", "/admin"):
            r_403 = await alice_client.get(forbidden_path)
            assert r_403.status_code == 403
            assert "Access Denied" in r_403.text

    # Reusing the same invite link fails (single-use)
    async with _new_client() as bob_client:
        again = await bob_client.get(f"/register?code={code}")
        assert again.status_code == 200
        assert "invalid, expired, or has already been used" in again.text
        bob_csrf = _csrf_from_html((await bob_client.get("/login")).text)
        post_again = await bob_client.post(
            "/register",
            data={
                "code": code,
                "username": "bob",
                "password": "bob-strong-password",
                "confirm_password": "bob-strong-password",
                "csrf_token": bob_csrf,
            },
        )
        assert post_again.status_code == 400


async def test_strict_tenant_isolation_idor_and_per_user_api_tokens(admin_user):
    alice = database.db_create_user("alice", auth.hash_password("alice-strong-password"))

    # Both users add the same word and capture the same URL
    admin_eid = database.db_add_entry(
        admin_user.id,
        "Admin context - ephemeral",
        definition_text="Admin definition",
        example_text="> Admin says ephemeral things fade away quickly.",
    )
    admin_def_id = database.db_get_entry_by_id(admin_user.id, admin_eid).definitions[0].id
    admin_note, admin_item = database.db_add_capture_item(
        admin_user.id,
        "https://www.youtube.com/watch?v=VeHFu956WKE",
        "Video",
        "adminword",
        "admin ctx",
    )

    alice_eid = database.db_add_entry(
        alice.id,
        "Alice context - ephemeral",
        definition_text="Alice definition",
    )
    assert alice_eid != admin_eid

    async with _new_client() as alice_client:
        await _login_as(alice_client, "alice", "alice-strong-password")
        csrf = _csrf_from_html((await alice_client.get("/add_entry")).text)
        hdrs = {"X-CSRF-Token": csrf}

        # Alice cannot read, edit, delete, bookmark, quiz, or add definitions to admin's entry
        assert (await alice_client.get(f"/entry/{admin_eid}")).status_code == 404
        assert (await alice_client.get(f"/edit_entry/{admin_eid}")).status_code == 404
        assert (await alice_client.get(f"/edit_example/{admin_eid}")).status_code == 404
        assert (await alice_client.get(f"/edit_definition/{admin_def_id}")).status_code == 404
        assert (await alice_client.get(f"/add_definition?entry_id={admin_eid}")).status_code == 404
        assert (await alice_client.get(f"/show_synonyms/{admin_eid}")).status_code == 404
        assert (await alice_client.delete(f"/delete_entry/{admin_eid}", headers=hdrs)).status_code == 404
        assert (await alice_client.delete(f"/delete_definition/{admin_def_id}", headers=hdrs)).status_code == 404
        assert (await alice_client.post(f"/entry/{admin_eid}/set_review_bookmark", headers=hdrs)).status_code == 404
        assert (await alice_client.post(f"/quiz/{admin_eid}/seen", headers=hdrs)).status_code == 404
        assert (
            await alice_client.post(
                "/add_definition",
                data={"entry_id": admin_eid, "definition_text": "hijack", "csrf_token": csrf},
            )
        ).status_code == 404

        # Alice cannot touch admin's page notes or capture items via /api/v1/*
        assert (
            await alice_client.patch(
                f"/api/v1/page-note/items/{admin_item.id}",
                json={"word": "hacked"},
                headers=hdrs,
            )
        ).status_code == 404
        assert (
            await alice_client.delete(
                f"/api/v1/page-note/items/{admin_item.id}", headers=hdrs
            )
        ).status_code == 404
        assert (
            await alice_client.delete(
                f"/api/v1/page-note/{admin_note.id}", headers=hdrs
            )
        ).status_code == 404
        prom = await alice_client.post(
            "/api/v1/page-note/promote",
            json={"item_ids": [admin_item.id]},
            headers=hdrs,
        )
        assert prom.status_code == 200
        assert prom.json()["results"] == [{"item_id": admin_item.id, "status": "not_found"}]

        # Alice's quiz never serves admin's entry
        q_resp = await alice_client.get("/quiz/next")
        assert q_resp.json() == {"question": None}

        # Alice creates a per-device API token on /account and uses it via Bearer auth
        acc = await alice_client.get("/account")
        acc_csrf = _csrf_from_html(acc.text)
        tok_resp = await alice_client.post(
            "/account/tokens",
            data={"label": "Alice Laptop", "csrf_token": acc_csrf},
        )
        assert tok_resp.status_code == 200
        tok_match = re.search(r'id="new-api-token" value="([^"]+)"', tok_resp.text)
        assert tok_match
        alice_token = tok_match.group(1)
        assert len(alice_token) >= 32

        async with _new_client() as ext_client:
            lookup = await ext_client.get(
                "/api/v1/lookup?word=ephemeral",
                headers={"Authorization": f"Bearer {alice_token}"},
            )
            assert lookup.status_code == 200
            assert [e["id"] for e in lookup.json()["existing_entries"]] == [alice_eid]

            pn = await ext_client.get(
                "/api/v1/page-note?url=https://www.youtube.com/watch?v=VeHFu956WKE",
                headers={"Authorization": f"Bearer {alice_token}"},
            )
            assert pn.status_code == 200
            assert pn.json()["items"] == []

        # Revoking the token immediately rejects Bearer auth
        token_id = database.db_list_api_tokens(alice.id)[0].id
        rev = await alice_client.post(
            f"/account/tokens/{token_id}/revoke",
            data={"csrf_token": _csrf_from_html((await alice_client.get("/account")).text)},
        )
        assert rev.status_code == 303

        async with _new_client() as ext_client:
            r_revoked = await ext_client.get(
                "/api/v1/lookup?word=ephemeral",
                headers={"Authorization": f"Bearer {alice_token}"},
            )
            assert r_revoked.status_code == 401


async def test_password_change_admin_reset_and_disable_invalidate_sessions(admin_user):
    alice = database.db_create_user("alice", auth.hash_password("initial-password-1"))
    raw_api_tok, api_digest = auth.generate_opaque_token()
    database.db_create_api_token(alice.id, "Alice Chrome", api_digest)

    async with _new_client() as alice_a, _new_client() as alice_b, _new_client() as admin_c:
        await _login_as(alice_a, "alice", "initial-password-1")
        await _login_as(alice_b, "alice", "initial-password-1")

        # Changing password on session A keeps A logged in and invalidates B
        acc_csrf = _csrf_from_html((await alice_a.get("/account")).text)
        ch = await alice_a.post(
            "/account/password",
            data={
                "current_password": "initial-password-1",
                "new_password": "updated-password-2",
                "confirm_password": "updated-password-2",
                "csrf_token": acc_csrf,
            },
        )
        assert ch.status_code == 200
        assert "Password updated" in ch.text
        assert (await alice_a.get("/")).status_code == 200
        assert (await alice_b.get("/")).status_code == 303

        # Admin issues a one-time reset link for Alice
        await _login_as(admin_c, "test-admin", "correct horse battery staple")
        admin_csrf = _csrf_from_html((await admin_c.get("/admin")).text)
        reset_resp = await admin_c.post(
            f"/admin/users/{alice.id}/reset-link",
            data={"csrf_token": admin_csrf},
        )
        assert reset_resp.status_code == 200
        reset_match = re.search(r'id="created-reset-url" value="([^"]+)"', reset_resp.text)
        assert reset_match
        reset_token = reset_match.group(1).split("token=", 1)[1]

        async with _new_client() as reset_c:
            r_get = await reset_c.get(f"/reset-password?token={reset_token}")
            assert r_get.status_code == 200
            assert r_get.headers.get("referrer-policy") == "no-referrer"
            r_csrf = _csrf_from_html(r_get.text)
            r_post = await reset_c.post(
                "/reset-password",
                data={
                    "token": reset_token,
                    "password": "reset-password-3",
                    "confirm_password": "reset-password-3",
                    "csrf_token": r_csrf,
                },
            )
            assert r_post.status_code == 303
            assert r_post.headers["location"] == "/login?reset=1"

            # Reset link cannot be reused
            r_again = await reset_c.get(f"/reset-password?token={reset_token}")
            assert "invalid, expired, or has already been used" in r_again.text

        # Session A is now invalidated after password reset
        assert (await alice_a.get("/")).status_code == 303

        # Alice logs in with new password
        await _login_as(alice_a, "alice", "reset-password-3")

        # Admin cannot disable themselves
        self_dis = await admin_c.post(
            f"/admin/users/{admin_user.id}/toggle-active",
            data={"csrf_token": _csrf_from_html((await admin_c.get("/admin")).text)},
        )
        assert self_dis.status_code == 400

        # Admin disables Alice -> both browser session and API Bearer token stop working
        dis = await admin_c.post(
            f"/admin/users/{alice.id}/toggle-active",
            data={"csrf_token": _csrf_from_html((await admin_c.get("/admin")).text)},
        )
        assert dis.status_code == 303
        assert (await alice_a.get("/")).status_code == 303

        async with _new_client() as ext_c:
            r_tok = await ext_c.get(
                "/api/v1/page-note?url=https://example.com/a",
                headers={"Authorization": f"Bearer {raw_api_tok}"},
            )
            assert r_tok.status_code == 401

        # Disabled user cannot log in (generic error)
        async with _new_client() as login_c:
            l_csrf = _csrf_from_html((await login_c.get("/login")).text)
            bad = await login_c.post(
                "/login",
                data={
                    "username": "alice",
                    "password": "reset-password-3",
                    "next_path": "/",
                    "csrf_token": l_csrf,
                },
            )
            assert bad.status_code == 401
            assert "Invalid username or password" in bad.text


async def test_markdown_xss_sanitized_while_ipa_spans_preserved(
    client, admin_user, monkeypatch
):
    await _login_as(client, "test-admin", "correct horse battery staple")
    monkeypatch.setattr(main, "get_IPA", lambda w: "ˈkændər")

    eid = database.db_add_entry(
        admin_user.id,
        "ctx - candor",
        definition_text=(
            '**Honest** <script>alert("xss")</script> '
            '<img src=x onerror="alert(1)"> '
            '[bad](javascript:alert(1)) [ok](https://example.com)'
        ),
        example_text=(
            '> Say /ˈkændər/ clearly <script>boom()</script> '
            '<span class="evil">hi</span>'
        ),
    )

    resp = await client.get(f"/entry/{eid}")
    assert resp.status_code == 200
    assert 'alert("xss")' not in resp.text
    assert "boom()" not in resp.text
    assert "onerror=" not in resp.text
    assert "javascript:alert" not in resp.text
    assert 'class="evil"' not in resp.text
    assert "<strong>Honest</strong>" in resp.text
    assert 'href="https://example.com"' in resp.text
    assert '<span class="ipa">/ˈkændər/</span>' in resp.text

    # Direct sanitizer check: no <script> tag survives render_safe_markdown
    direct = main.render_safe_markdown(
        '<script>alert(1)</script> Say /ˈkændər/', wrap_ipa=True
    )
    assert "<script" not in direct.lower()
    assert "alert(1)" not in direct
    assert '<span class="ipa">/ˈkændər/</span>' in direct


async def test_login_rate_limiting(client):
    page = await client.get("/login")
    csrf = _csrf_from_html(page.text)

    for _ in range(10):
        resp = await client.post(
            "/login",
            data={
                "username": "test-admin",
                "password": "wrong-password",
                "next_path": "/",
                "csrf_token": csrf,
            },
        )
        assert resp.status_code == 401

    throttled = await client.post(
        "/login",
        data={
            "username": "test-admin",
            "password": "correct horse battery staple",
            "next_path": "/",
            "csrf_token": csrf,
        },
    )
    assert throttled.status_code == 429

    # Different username from same IP is NOT locked out by one user's mistypes
    database.db_create_user("friend", auth.hash_password("friend-secret-pw"))
    other = await client.post(
        "/login",
        data={
            "username": "friend",
            "password": "friend-secret-pw",
            "next_path": "/",
            "csrf_token": csrf,
        },
    )
    assert other.status_code == 303


async def test_per_user_account_export_json_and_markdown(admin_user):
    import json

    # Admin private data that must never leak into Alice's export
    admin_entry_id = database.db_add_entry(
        admin_user.id,
        "Admin private context - clandestine",
        definition_text="Kept secret.",
    )
    database.db_upsert_page_note(
        admin_user.id,
        "https://example.com/admin-only",
        "Admin Article",
        "Admin private scratchpad",
    )

    alice = database.db_create_user("alice", auth.hash_password("alice-password-10"))
    a1 = database.db_add_entry(
        alice.id,
        "We got a lot of mileage out of that model. - mileage",
        definition_text="Practical value /mˈaɪlɪdʒ/.",
        example_text="> How much mileage can you get out of it?",
    )
    database.db_add_definition(alice.id, a1, "Secondary sense.")
    a2 = database.db_add_entry(alice.id, "laconic")
    database.db_set_review_bookmark(alice.id, a1)
    database.db_upsert_page_note(
        alice.id,
        "https://example.com/alice-read",
        "Alice Reading",
        "Alice scratchpad note",
    )
    database.db_add_capture_item(
        alice.id,
        normalized_url="https://example.com/alice-read",
        title="Alice Reading",
        word="terse",
        context="A terse reply.",
        definition_text="",
        timestamp_seconds=None,
    )

    # Unauthenticated browser clicks redirect 303 to /login?next=... (not raw 401 JSON)
    async with _new_client() as anon_c:
        r_json_nav = await anon_c.get(
            "/account/export.json", headers={"Accept": "text/html"}
        )
        assert r_json_nav.status_code == 303
        assert "/login?next=%2Faccount%2Fexport.json" in r_json_nav.headers["location"]

        r_md_nav = await anon_c.get(
            "/account/export.md", headers={"Accept": "text/html"}
        )
        assert r_md_nav.status_code == 303
        assert "/login?next=%2Faccount%2Fexport.md" in r_md_nav.headers["location"]

        r_api = await anon_c.get(
            "/account/export.json", headers={"Accept": "application/json"}
        )
        assert r_api.status_code == 401

    async with _new_client() as alice_c:
        await _login_as(alice_c, "alice", "alice-password-10")

        acct = await alice_c.get("/account")
        assert acct.status_code == 200
        assert 'href="/account/export.json"' in acct.text
        assert 'href="/account/export.md"' in acct.text
        assert "download=" not in acct.text
        assert "2 entries" in acct.text

        # Cross-site navigation is rejected with 403
        cross = await alice_c.get(
            "/account/export.json", headers={"Sec-Fetch-Site": "cross-site"}
        )
        assert cross.status_code == 403

        json_resp = await alice_c.get("/account/export.json")
        assert json_resp.status_code == 200
        assert "application/json" in json_resp.headers["content-type"]
        assert 'attachment; filename="glossbook-alice-' in json_resp.headers["content-disposition"]
        assert json_resp.headers["cache-control"] == "no-store"
        assert json_resp.headers["x-content-type-options"] == "nosniff"
        assert "password_hash" not in json_resp.text
        assert "clandestine" not in json_resp.text
        assert "Admin private scratchpad" not in json_resp.text

        data = json.loads(json_resp.text)
        assert data["app"] == "Glossbook"
        assert data["username"] == "alice"
        assert data["entry_count"] == 2
        assert data["review_bookmark_entry_id"] == a1
        assert [e["word"] for e in data["entries"]] == ["laconic", "mileage"]
        mileage_entry = data["entries"][1]
        assert mileage_entry["definitions"] == [
            "Practical value /mˈaɪlɪdʒ/.",
            "Secondary sense.",
        ]
        assert len(data["inbox_page_notes"]) == 1
        assert data["inbox_page_notes"][0]["notes_md"] == "Alice scratchpad note"
        assert data["inbox_page_notes"][0]["items"][0]["word"] == "terse"

        # Dangling bookmark ID (e.g. pointing to another/hidden row) normalizes to None
        database.db_set_review_bookmark(alice.id, a2)
        with database.Session(database.engine) as s:
            row = s.get(database.Entry, a2)
            row.is_hidden = True
            s.commit()
        json_after_hide = json.loads((await alice_c.get("/account/export.json")).text)
        assert json_after_hide["review_bookmark_entry_id"] is None
        assert admin_entry_id not in {e["id"] for e in json_after_hide["entries"]}

        md_resp = await alice_c.get("/account/export.md")
        assert md_resp.status_code == 200
        assert "text/markdown" in md_resp.headers["content-type"]
        assert 'attachment; filename="glossbook-alice-' in md_resp.headers["content-disposition"]
        assert "# Glossbook — alice" in md_resp.text
        assert "## mileage" in md_resp.text
        assert "> **Context:** We got a lot of mileage out of that model." in md_resp.text
        assert "### Definition" in md_resp.text
        assert "### Example" in md_resp.text
        assert "clandestine" not in md_resp.text


async def test_extension_onboarding_dismisses_after_token_created(admin_user):
    bob = database.db_create_user("bob", auth.hash_password("bob-password-10"))

    async with _new_client() as bob_c:
        await _login_as(bob_c, "bob", "bob-password-10")

        dash_before = await bob_c.get("/")
        assert dash_before.status_code == 200
        assert "extension-promo-card" in dash_before.text
        assert main.EXTENSION_DOWNLOAD_URL in dash_before.text
        assert 'href="/account#extension"' in dash_before.text

        acct_before = await bob_c.get("/account")
        assert '<details class="extension-guide" open>' in acct_before.text
        assert main.EXTENSION_DOWNLOAD_URL in acct_before.text

        inbox_empty = await bob_c.get("/inbox")
        assert 'href="/account#extension"' in inbox_empty.text

        # Creating an API token dismisses the dashboard promo and collapses the guide
        _, digest = auth.generate_opaque_token()
        database.db_create_api_token(bob.id, "Laptop", digest)

        dash_after = await bob_c.get("/")
        assert "extension-promo-card" not in dash_after.text

        acct_after = await bob_c.get("/account")
        assert '<details class="extension-guide">' in acct_after.text
        assert '<details class="extension-guide" open>' not in acct_after.text
