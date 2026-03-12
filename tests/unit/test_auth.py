"""
Unit tests for authentication middleware.
"""

import os
import pytest

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-unit-tests")


class TestAuth:

    def test_create_access_token(self):
        from app.middleware.auth import create_access_token

        token = create_access_token(data={"sub": "user-123"})
        assert isinstance(token, str)
        assert len(token) > 20

    def test_create_refresh_token(self):
        from app.middleware.auth import create_refresh_token

        token = create_refresh_token(data={"sub": "user-123"})
        assert isinstance(token, str)
        assert len(token) > 20

    def test_access_and_refresh_tokens_differ(self):
        from app.middleware.auth import create_access_token, create_refresh_token

        access = create_access_token(data={"sub": "user-123"})
        refresh = create_refresh_token(data={"sub": "user-123"})
        assert access != refresh

    def test_verify_password(self):
        from app.middleware.auth import get_password_hash, verify_password

        hashed = get_password_hash("MySecretPass123")
        assert verify_password("MySecretPass123", hashed)
        assert not verify_password("WrongPassword", hashed)

    def test_password_hash_is_unique(self):
        from app.middleware.auth import get_password_hash

        h1 = get_password_hash("same-password")
        h2 = get_password_hash("same-password")
        # bcrypt produces different salts each time
        assert h1 != h2

    def test_token_contains_subject(self):
        from jose import jwt
        from app.middleware.auth import create_access_token
        from app.config import get_settings

        settings = get_settings()
        token = create_access_token(data={"sub": "user-abc"})
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        assert payload["sub"] == "user-abc"
        assert "exp" in payload
