"""
Shared test fixtures and configuration.
"""

import asyncio
import os
from typing import AsyncGenerator, Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient


# ---------------------------------------------------------------------------
# Event-loop fixture (session-scoped so async fixtures work everywhere)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# ---------------------------------------------------------------------------
# Mock Prisma client
# ---------------------------------------------------------------------------

@pytest.fixture()
def mock_prisma():
    """Return a mock Prisma client with common model stubs."""
    client = MagicMock()

    # Stub every model attribute so attribute access never raises
    for model in (
        "user", "paper", "paperchunk", "chatsession", "chatmessage",
        "researchnote", "citation", "topiccluster", "papercluster",
        "papersummary", "paperinsight", "papermetadata", "paperreference",
        "collection", "collectionitem", "readinglistitem", "annotation",
        "papercomparison", "activitylog",
    ):
        model_mock = AsyncMock()
        setattr(client, model, model_mock)

    # Prisma utility methods
    client.connect = AsyncMock()
    client.disconnect = AsyncMock()
    client.query_raw = AsyncMock(return_value=[])
    client.execute_raw = AsyncMock(return_value=0)

    return client


# ---------------------------------------------------------------------------
# FastAPI test client (uses mock DB by default)
# ---------------------------------------------------------------------------

@pytest.fixture()
async def client(mock_prisma) -> AsyncGenerator[AsyncClient, None]:
    """Async HTTP client wired to the FastAPI app with a mock database."""
    # Set required env vars BEFORE importing the app
    os.environ.setdefault("SECRET_KEY", "test-secret-key-for-unit-tests")
    os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test")
    os.environ.setdefault("APP_ENV", "testing")

    with patch("app.database.prisma_client.prisma", mock_prisma):
        from app.main import app  # noqa: delay import after env setup

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

@pytest.fixture()
def auth_headers() -> dict[str, str]:
    """Generate a valid JWT for testing authenticated endpoints."""
    os.environ.setdefault("SECRET_KEY", "test-secret-key-for-unit-tests")

    from app.middleware.auth import create_access_token

    token = create_access_token(data={"sub": "test-user-id-123"})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def sample_user() -> dict:
    return {
        "id": "test-user-id-123",
        "email": "test@example.com",
        "fullName": "Test User",
        "role": "RESEARCHER",
        "isActive": True,
    }


@pytest.fixture()
def sample_paper() -> dict:
    return {
        "id": "test-paper-id-456",
        "title": "Attention Is All You Need",
        "authors": ["Vaswani, A.", "Shazeer, N."],
        "abstract": "We propose a new simple network architecture, the Transformer.",
        "status": "COMPLETED",
        "userId": "test-user-id-123",
        "pageCount": 15,
        "fileHash": "abc123",
        "fileName": "attention.pdf",
    }
