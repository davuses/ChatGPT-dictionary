import os

import pytest
from httpx import ASGITransport, AsyncClient


os.environ.setdefault("DICTIONARY_ADMIN_USERNAME", "test-admin")
os.environ.setdefault(
    "DICTIONARY_ADMIN_PASSWORD_HASH",
    "$argon2id$v=19$m=65536,t=3,p=4$4sOvaQHchgzGdiRLpiaQQA$"
    "Ce21Qdouf1AflTvk6wEk9LZQdIcxSDf9jCvQANpi2f4",
)
os.environ.setdefault(
    "DICTIONARY_SESSION_SECRET", "test-session-secret-at-least-32-characters"
)

from main import app  # noqa: E402


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
