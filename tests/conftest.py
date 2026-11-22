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

import database  # noqa: E402
from main import app  # noqa: E402
import utils  # noqa: E402


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
