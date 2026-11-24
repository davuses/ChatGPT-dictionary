import random
import re

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

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
            "next_path": "/",
            "csrf_token": csrf_token,
        },
    )
    assert response.status_code == 303


def test_quiz_weight_prioritizes_unseen_and_neglected_entries():
    now = 1_750_000_000
    day = 86400

    unseen_legacy = utils._quiz_weight(0, None, now)
    unseen_added_two_days_ago = utils._quiz_weight(0, now - 2 * day, now)
    just_added = utils._quiz_weight(0, now - 3600, now)
    just_reviewed = utils._quiz_weight(1, now - 3600, now)
    visited_once_week_ago = utils._quiz_weight(1, now - 7 * day, now)
    visited_once_half_year_ago = utils._quiz_weight(1, now - 180 * day, now)
    visited_five_half_year_ago = utils._quiz_weight(5, now - 180 * day, now)
    legacy_nonzero_null_ts = utils._quiz_weight(2, None, now)

    assert unseen_legacy == unseen_added_two_days_ago
    assert unseen_legacy > visited_once_half_year_ago
    assert visited_once_half_year_ago > visited_once_week_ago
    assert visited_once_half_year_ago > visited_five_half_year_ago
    assert visited_once_week_ago > just_added > just_reviewed > 0
    assert legacy_nonzero_null_ts > 0


def test_pick_weighted_candidate_prefers_neglected_and_respects_exclusions():
    now = 1_750_000_000
    day = 86400
    pool = [
        utils.QuizCandidate(1, "unseen", ["This is an unseen word in context."]),
        utils.QuizCandidate(2, "drilled", ["This is a drilled word in context."]),
        utils.QuizCandidate(3, "stale", ["This is a stale deleted word in context."]),
    ]
    visit_stats = {
        1: (0, None),
        2: (5, now - 3600),
        # entry 3 intentionally missing (deleted/hidden after cache warm)
    }

    rng = random.Random(42)
    picks = [
        utils._pick_weighted_candidate(pool, visit_stats, now=now, rng=rng).entry_id
        for _ in range(200)
    ]
    assert 3 not in picks
    assert picks.count(1) > 180

    # Excluding entry 1 forces entry 2; excluding both falls back to active pool (never stale 3)
    only_two = utils._pick_weighted_candidate(
        pool, visit_stats, exclude_entry_ids={1}, now=now, rng=random.Random(1)
    )
    assert only_two is not None and only_two.entry_id == 2

    fallback = utils._pick_weighted_candidate(
        pool, visit_stats, exclude_entry_ids={1, 2}, now=now, rng=random.Random(1)
    )
    assert fallback is not None and fallback.entry_id in {1, 2}


def test_example_sentences_and_blank_word():
    example = (
        "a brief gloss of the word\n\n"
        "*fit in with*\n\n"
        "SYN: blend in, harmonize\n\n"
        "> She tried to fit in with her new teammates right away.\n\n"
        "> They wanted to fit in with the crowd, hoping to fit in with ease."
    )
    sentences = utils._example_sentences(example)
    assert sentences == [
        "She tried to fit in with her new teammates right away.",
        "They wanted to fit in with the crowd, hoping to fit in with ease.",
    ]

    blanked, display = utils._blank_word(sentences[1], "Fit in with")
    assert display == "fit in with"
    assert blanked == "They wanted to _____ the crowd, hoping to _____ ease."


def test_db_record_entry_visit_handles_null_and_cooldown(admin_user):
    with Session(database.engine) as session:
        e1 = database.Entry(
            user_id=admin_user.id, text="ctx - alpha", visit_count=None, last_visit=None
        )
        e2 = database.Entry(
            user_id=admin_user.id, text="ctx - hidden", is_hidden=True, visit_count=0
        )
        session.add_all([e1, e2])
        session.commit()
        e1_id, e2_id = e1.id, e2.id

    t0 = 1_750_000_000
    assert database.db_record_entry_visit(admin_user.id, e1_id, now=t0) is True
    assert database.db_record_entry_visit(admin_user.id, e1_id, now=t0 + 3600) is False
    assert database.db_record_entry_visit(admin_user.id, e1_id, now=t0 + 3600 * 12) is True
    assert database.db_record_entry_visit(admin_user.id, e2_id, now=t0) is None
    assert database.db_record_entry_visit(admin_user.id, 999999, now=t0) is None

    stats = database.db_get_entry_visit_stats(admin_user.id)
    assert stats == {e1_id: (2, t0 + 3600 * 12)}


async def test_dashboard_and_quiz_next_do_not_mutate_visits(client, monkeypatch):
    await _login(client)
    question = main.QuizQuestion(42, "serendipity", "It was pure _____ to meet there.")
    monkeypatch.setattr(main, "pick_random_question", lambda *_a, **_kw: question)
    monkeypatch.setattr(main, "db_count_entries", lambda _uid: 10)
    monkeypatch.setattr(main, "db_count_entries_visited_since", lambda _uid, _ts: 2)
    monkeypatch.setattr(main, "get_review_bookmark", lambda _uid: None)
    recorded_calls = []
    monkeypatch.setattr(
        main,
        "db_record_entry_visit",
        lambda _uid, entry_id: recorded_calls.append(entry_id) or True,
    )

    root = await client.get("/")
    assert root.status_code == 200
    assert 'data-entry-id="42"' in root.text

    nxt = await client.get("/quiz/next?exclude=1,2")
    assert nxt.status_code == 200
    assert nxt.json()["entry_id"] == 42
    assert recorded_calls == []


async def test_quiz_seen_endpoint_enforces_auth_csrf_and_records_visit(
    client, monkeypatch
):
    assert (await client.post("/quiz/42/seen")).status_code == 401

    await _login(client)
    root = await client.get("/")
    csrf_token = _csrf_from_html(root.text)

    assert (await client.post("/quiz/42/seen")).status_code == 403

    calls = []
    monkeypatch.setattr(
        main,
        "db_record_entry_visit",
        lambda _uid, entry_id: calls.append(entry_id) or (True if entry_id == 42 else None),
    )

    ok = await client.post("/quiz/42/seen", headers={"X-CSRF-Token": csrf_token})
    assert ok.status_code == 200
    assert ok.json() == {"recorded": True}
    assert calls == [42]

    missing = await client.post("/quiz/999999/seen", headers={"X-CSRF-Token": csrf_token})
    assert missing.status_code == 404


def test_pick_weighted_candidates_without_replacement_and_extreme_cooldown():
    now = 1_750_000_000
    pool = [
        utils.QuizCandidate(1, "alpha", ["Alpha appears in a full context sentence."]),
        utils.QuizCandidate(2, "beta", ["Beta appears in a full context sentence."]),
        utils.QuizCandidate(3, "gamma", ["Gamma appears in a full context sentence."]),
        utils.QuizCandidate(4, "ghost", ["Deleted entry missing from visit stats."]),
    ]
    # Entry 2 & 3 have tiny cooldown weights where naive u**(1/w) would underflow float to 0.0
    visit_stats = {
        1: (0, None),
        2: (250, now - 60),
        3: (300, now - 30),
    }

    picked, active_count = utils._pick_weighted_candidates(
        pool, visit_stats, limit=10, now=now, rng=random.Random(7)
    )
    assert active_count == 3
    assert len(picked) == 3
    assert len({c.entry_id for c in picked}) == 3
    assert 4 not in {c.entry_id for c in picked}

    # Prefers non-excluded candidates first, then tops up from excluded without duplicates
    topped_up, _ = utils._pick_weighted_candidates(
        pool,
        visit_stats,
        limit=2,
        exclude_entry_ids={1, 2},
        now=now,
        rng=random.Random(7),
    )
    assert len(topped_up) == 2
    assert topped_up[0].entry_id == 3
    assert topped_up[1].entry_id in {1, 2}


async def test_review_session_route_sanitization_isolation_and_readonly(
    client, admin_user
):
    import json

    unauth = await client.get("/review")
    assert unauth.status_code == 303
    assert "/login?next=%2Freview" in unauth.headers["location"]

    await _login(client)

    empty_resp = await client.get("/review")
    assert empty_resp.status_code == 200
    assert "No quizzable entries yet" in empty_resp.text

    e1 = database.db_add_entry(
        admin_user.id,
        "We got a lot of mileage out of that simple model. - mileage",
        definition_text="Usefulness /mˈaɪlɪdʒ/ <script>alert(1)</script> and literal </script> tag.",
    )
    database.db_add_definition(admin_user.id, e1, "Second definition should not override first.")
    e2 = database.db_add_entry(
        admin_user.id,
        "The joke was completely lost on Chris at dinner. - lost on",
    )
    e3 = database.db_add_entry(
        admin_user.id,
        "Don't skimp on winter tires before driving north. - skimp",
        definition_text="Spend less than needed.",
    )

    other_user = database.db_create_user("other-member", "hash")
    other_entry = database.db_add_entry(
        other_user.id,
        "Their private word stays completely isolated here. - arcane",
        definition_text="Secret.",
    )
    utils.invalidate_quiz_pool_cache()

    root = await client.get("/")
    assert 'href="/review"' in root.text

    before_stats = database.db_get_entry_visit_stats(admin_user.id)
    resp = await client.get(f"/review?size=2&exclude={e3}")
    assert resp.status_code == 200
    assert resp.headers.get("cache-control") == "private, no-cache"
    assert "style.css" in resp.text
    assert database.db_get_entry_visit_stats(admin_user.id) == before_stats

    deck_match = re.search(
        r'<script type="application/json" id="review-deck-data">(.*?)</script>',
        resp.text,
        re.DOTALL,
    )
    assert deck_match
    deck = json.loads(deck_match.group(1))
    assert len(deck) == 2
    returned_ids = {card["entry_id"] for card in deck}
    assert returned_ids == {e1, e2}
    assert other_entry not in returned_ids

    by_id = {card["entry_id"]: card for card in deck}
    mileage_card = by_id[e1]
    assert mileage_card["headword"] == "mileage"
    assert mileage_card["blanked_sentence"] == "We got a lot of _____ out of that simple model."
    assert mileage_card["sentence_matches"] == ["mileage"]
    assert "<script>" not in mileage_card["definition_html"]
    assert '<span class="ipa">/mˈaɪlɪdʒ/</span>' in mileage_card["definition_html"]
    assert "Second definition" not in mileage_card["definition_html"]

    assert by_id[e2]["definition_html"] == ""

    assert "size=2" in resp.text
    assert f"exclude={e3}" in resp.text
