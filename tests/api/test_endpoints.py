"""
API endpoint tests for health and auth routes.
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-unit-tests")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test")
os.environ.setdefault("APP_ENV", "testing")


# =====================================================================
# Health endpoints
# =====================================================================

class TestHealthEndpoints:

    @pytest.mark.asyncio
    async def test_health_check(self, client):
        response = await client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_readiness_check(self, client):
        response = await client.get("/api/v1/health/ready")
        # May return 200 or 503 depending on mock DB state
        assert response.status_code in (200, 503)


# =====================================================================
# Auth endpoints
# =====================================================================

class TestAuthEndpoints:

    @pytest.mark.asyncio
    async def test_register_success(self, client, mock_prisma):
        mock_prisma.user.find_unique = AsyncMock(return_value=None)
        mock_prisma.user.create = AsyncMock(return_value=MagicMock(
            id="new-user-id",
            email="new@example.com",
            fullName="New User",
            role="RESEARCHER",
            isActive=True,
            createdAt="2024-01-01T00:00:00Z",
        ))

        response = await client.post("/api/v1/auth/register", json={
            "email": "new@example.com",
            "password": "StrongP@ss1",
            "full_name": "New User",
        })
        assert response.status_code in (200, 201)

    @pytest.mark.asyncio
    async def test_register_duplicate_email(self, client, mock_prisma):
        mock_prisma.user.find_unique = AsyncMock(return_value=MagicMock(
            id="existing-id",
            email="dup@example.com",
        ))

        response = await client.post("/api/v1/auth/register", json={
            "email": "dup@example.com",
            "password": "StrongP@ss1",
            "full_name": "Dup User",
        })
        assert response.status_code in (400, 409)

    @pytest.mark.asyncio
    async def test_login_invalid_credentials(self, client, mock_prisma):
        mock_prisma.user.find_unique = AsyncMock(return_value=None)

        response = await client.post("/api/v1/auth/login", json={
            "email": "nobody@example.com",
            "password": "WrongPass1!",
        })
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_profile_unauthenticated(self, client):
        response = await client.get("/api/v1/auth/profile")
        assert response.status_code == 401 or response.status_code == 403


# =====================================================================
# Paper endpoints (basic)
# =====================================================================

class TestPaperEndpoints:

    @pytest.mark.asyncio
    async def test_list_papers_unauthenticated(self, client):
        response = await client.get("/api/v1/papers")
        assert response.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_list_papers_authenticated(self, client, auth_headers, mock_prisma, sample_user):
        mock_prisma.user.find_unique = AsyncMock(return_value=MagicMock(**sample_user))
        mock_prisma.paper.find_many = AsyncMock(return_value=[])
        mock_prisma.paper.count = AsyncMock(return_value=0)

        response = await client.get("/api/v1/papers", headers=auth_headers)
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_get_paper_not_found(self, client, auth_headers, mock_prisma, sample_user):
        mock_prisma.user.find_unique = AsyncMock(return_value=MagicMock(**sample_user))
        mock_prisma.paper.find_first = AsyncMock(return_value=None)

        response = await client.get("/api/v1/papers/nonexistent-id", headers=auth_headers)
        assert response.status_code == 404
