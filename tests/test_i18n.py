import re
import time

import pytest

import database
import i18n
import utils


pytestmark = pytest.mark.anyio


def _csrf_from_html(html: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert match
    return match.group(1)


async def _login(client, next_path: str = "/"):
    login_page = await client.get(f"/login?next={next_path}")
    assert login_page.status_code == 200
    csrf_token = _csrf_from_html(login_page.text)
    resp = await client.post(
        "/login",
        data={
            "username": "test-admin",
            "password": "correct horse battery staple",
            "next_path": next_path,
            "csrf_token": csrf_token,
        },
    )
    assert resp.status_code == 303


def test_translation_catalog_parity():
    assert set(i18n.TRANSLATIONS["en"].keys()) == set(i18n.TRANSLATIONS["zh-CN"].keys())
    assert set(i18n.JS_TRANSLATIONS["en"].keys()) == set(
        i18n.JS_TRANSLATIONS["zh-CN"].keys()
    )


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        (None, "en"),
        ("", "en"),
        ("zh-CN,zh;q=0.9,en;q=0.8", "zh-CN"),
        ("zh-Hans", "zh-CN"),
        ("zh-TW,en;q=0.5", "zh-CN"),
        ("en-US,en;q=0.9,zh-CN;q=0.8", "en"),
        ("zh-CN;q=0, en;q=0.5", "en"),
        ("zh-CN;q=abc, en;q=0.5", "en"),
        ("fr-FR,de;q=0.8", "en"),
    ],
)
def test_parse_accept_language(header, expected):
    assert i18n.parse_accept_language(header) == expected


def test_how_long_ago_zh_cn():
    now = 1_700_000_000
    assert utils.get_how_long_ago(None, now=now, lang="zh-CN") == "从未"
    assert utils.get_how_long_ago(now - 30, now=now, lang="zh-CN") == "刚刚"
    assert utils.get_how_long_ago(now - 5 * 60, now=now, lang="zh-CN") == "5 分钟前"
    assert utils.get_how_long_ago(now - 3 * 3600, now=now, lang="zh-CN") == "3 小时前"
    assert utils.get_how_long_ago(now - 2 * 86400, now=now, lang="zh-CN") == "2 天前"


async def test_language_route_security_and_query_preservation(client):
    # Anonymous GET on a non-form page with Accept-Language renders Chinese
    # without minting a dictionary_session cookie.
    anon_zh = await client.get(
        "/does-not-exist-i18n-check",
        headers={"Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"},
    )
    assert anon_zh.status_code == 404
    assert '<html lang="zh-CN">' in anon_zh.text
    assert "页面不存在" in anon_zh.text
    set_cookie_hdr = anon_zh.headers.get("set-cookie", "").lower()
    assert "dictionary_session=" not in set_cookie_hdr

    # Anonymous GET /login also honors Accept-Language and preserves login CSRF
    login_zh = await client.get(
        "/login", headers={"Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"}
    )
    assert login_zh.status_code == 200
    assert '<html lang="zh-CN">' in login_zh.text
    assert "登录" in login_zh.text
    assert _csrf_from_html(login_zh.text)

    # Cross-site POST /language is blocked
    cross_site = await client.post(
        "/language",
        data={"lang": "zh-CN", "next_path": "/login"},
        headers={"Sec-Fetch-Site": "cross-site"},
    )
    assert cross_site.status_code == 403

    bad_origin = await client.post(
        "/language",
        data={"lang": "zh-CN", "next_path": "/login"},
        headers={"Origin": "https://evil.example"},
    )
    assert bad_origin.status_code == 403

    # Valid POST /language preserves invite query string and sets sensitive-token headers
    ok = await client.post(
        "/language",
        data={"lang": "zh-CN", "next_path": "/register?code=invite-token-123"},
        headers={"Origin": "https://dictionary.test"},
    )
    assert ok.status_code == 303
    assert ok.headers["location"] == "/register?code=invite-token-123"
    assert ok.headers.get("cache-control") == "no-store"
    assert ok.headers.get("referrer-policy") == "no-referrer"
    cookie = ok.headers["set-cookie"].lower()
    assert "glossbook_lang=zh-cn" in cookie
    assert "httponly" in cookie
    assert "samesite=lax" in cookie
    assert "secure" in cookie

    # Open redirect attempt is sanitized back to /
    evil_next = await client.post(
        "/language",
        data={"lang": "en", "next_path": "//evil.example/phish"},
    )
    assert evil_next.status_code == 303
    assert evil_next.headers["location"] == "/"


async def test_web_app_english_and_chinese_ui_and_words_nav(client, admin_user):
    entry_id = database.db_add_entry(
        admin_user.id,
        "resilient - She remained resilient under pressure.",
        "The resilient team bounced back quickly.",
    )
    database.db_add_definition(admin_user.id, entry_id, "Able to recover quickly.")
    utils.invalidate_words_cache(admin_user.id)
    utils.invalidate_quiz_pool_cache(admin_user.id)

    await _login(client)

    # Default English UI: nav says Words (not Browse), dashboard subtitle links to /entries
    dash_en = await client.get("/")
    assert dash_en.status_code == 200
    assert '<html lang="en">' in dash_en.text
    assert ">Words<" in dash_en.text
    assert ">Browse<" not in dash_en.text
    assert '<a class="subtitle-link" href="/entries">1 entry</a>' in dash_en.text

    # Switch to Chinese via POST /language
    sw = await client.post("/language", data={"lang": "zh-CN", "next_path": "/"})
    assert sw.status_code == 303

    dash_zh = await client.get("/")
    assert dash_zh.status_code == 200
    assert '<html lang="zh-CN">' in dash_zh.text
    assert ">词库<" in dash_zh.text
    assert ">收集箱<" in dash_zh.text
    assert "语境填空" in dash_zh.text
    assert "开始复习" in dash_zh.text
    assert '<a class="subtitle-link" href="/entries">1 个词条</a>' in dash_zh.text

    # /entries full page and live-search XHR render Chinese
    entries_zh = await client.get("/entries")
    assert entries_zh.status_code == 200
    assert "仅词条" in entries_zh.text
    assert "待补释义" in entries_zh.text

    xhr_zh = await client.get(
        "/entries?q=resilient", headers={"X-Requested-With": "XMLHttpRequest"}
    )
    assert xhr_zh.status_code == 200
    payload = xhr_zh.json()
    assert payload["count"] == 1
    assert "词条" in payload["results_html"]
    assert "语境" in payload["results_html"]

    # /review, /inbox, /account, /entry/{id}, /admin all render Chinese cleanly
    for path, expected_snippet in (
        ("/review", "专注复习"),
        ("/inbox", "收集箱"),
        ("/account", "导出与导入词库"),
        (f"/entry/{entry_id}", "上次查看："),
        ("/admin", "管理邀请链接与用户账户"),
    ):
        resp = await client.get(path)
        assert resp.status_code == 200, f"{path} returned {resp.status_code}"
        assert '<html lang="zh-CN">' in resp.text
        assert expected_snippet in resp.text

    # Switch back to English
    sw_en = await client.post("/language", data={"lang": "en", "next_path": "/"})
    assert sw_en.status_code == 303
    dash_back = await client.get("/")
    assert '<html lang="en">' in dash_back.text
    assert "Fill in the blank" in dash_back.text
