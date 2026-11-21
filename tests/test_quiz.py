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


def test_db_record_entry_visit_handles_null_and_cooldown(monkeypatch):
    test_engine = create_engine("sqlite:///:memory:", future=True)
    database.Base.metadata.create_all(test_engine)
    monkeypatch.setattr(database, "engine", test_engine)

    with Session(test_engine) as session:
        e1 = database.Entry(text="ctx - alpha", visit_count=None, last_visit=None)
        e2 = database.Entry(text="ctx - hidden", is_hidden=True, visit_count=0)
        session.add_all([e1, e2])
        session.commit()
        e1_id, e2_id = e1.id, e2.id

    t0 = 1_750_000_000
    assert database.db_record_entry_visit(e1_id, now=t0) is True
    assert database.db_record_entry_visit(e1_id, now=t0 + 3600) is False
    assert database.db_record_entry_visit(e1_id, now=t0 + 3600 * 12) is True
    assert database.db_record_entry_visit(e2_id, now=t0) is None
    assert database.db_record_entry_visit(999999, now=t0) is None

    stats = database.db_get_entry_visit_stats()
    assert stats == {e1_id: (2, t0 + 3600 * 12)}


async def test_dashboard_and_quiz_next_do_not_mutate_visits(client, monkeypatch):
    await _login(client)
    question = main.QuizQuestion(42, "serendipity", "It was pure _____ to meet there.")
    monkeypatch.setattr(main, "pick_random_question", lambda **_: question)
    monkeypatch.setattr(main, "db_count_entries", lambda: 10)
    monkeypatch.setattr(main, "db_count_entries_visited_since", lambda _: 2)
    monkeypatch.setattr(main, "get_review_bookmark", lambda: None)
    recorded_calls = []
    monkeypatch.setattr(
        main, "db_record_entry_visit", lambda entry_id: recorded_calls.append(entry_id) or True
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
        lambda entry_id: calls.append(entry_id) or (True if entry_id == 42 else None),
    )

    ok = await client.post("/quiz/42/seen", headers={"X-CSRF-Token": csrf_token})
    assert ok.status_code == 200
    assert ok.json() == {"recorded": True}
    assert calls == [42]

    missing = await client.post("/quiz/999999/seen", headers={"X-CSRF-Token": csrf_token})
    assert missing.status_code == 404
