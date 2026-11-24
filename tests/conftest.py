import os

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine


os.environ.setdefault("DICTIONARY_ADMIN_USERNAME", "test-admin")
os.environ.setdefault(
    "DICTIONARY_ADMIN_PASSWORD_HASH",
    "$argon2id$v=19$m=65536,t=3,p=4$4sOvaQHchgzGdiRLpiaQQA$"
    "Ce21Qdouf1AflTvk6wEk9LZQdIcxSDf9jCvQANpi2f4",
)
os.environ.setdefault(
    "DICTIONARY_SESSION_SECRET", "test-session-secret-at-least-32-characters"
)
os.environ.setdefault("DICTIONARY_HTTPS_ONLY", "true")

import auth  # noqa: E402
import database  # noqa: E402
from main import app  # noqa: E402
import thesaurus  # noqa: E402
import utils  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_db(monkeypatch, tmp_path):
    db_path = tmp_path / "test.db"
    test_engine = create_engine(
        f"sqlite:///{db_path}",
        future=True,
        connect_args={"check_same_thread": False},
    )
    monkeypatch.setattr(database, "engine", test_engine)
    database.bootstrap_database(
        admin_username=os.environ["DICTIONARY_ADMIN_USERNAME"],
        admin_password_hash=os.environ["DICTIONARY_ADMIN_PASSWORD_HASH"],
        target_engine=test_engine,
    )
    auth.clear_all_rate_limits()
    utils.invalidate_words_cache()
    utils.invalidate_quiz_pool_cache()
    thesaurus.fetch_thesaurus_senses.cache_clear()
    try:
        yield test_engine
    finally:
        auth.clear_all_rate_limits()
        utils.invalidate_words_cache()
        utils.invalidate_quiz_pool_cache()
        thesaurus.fetch_thesaurus_senses.cache_clear()
        test_engine.dispose()


@pytest.fixture
def admin_user(isolated_db) -> database.UserRecord:
    user = database.db_get_user_by_username(os.environ["DICTIONARY_ADMIN_USERNAME"])
    assert user is not None
    return user


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="https://dictionary.test",
        follow_redirects=False,
    ) as test_client:
        yield test_client
