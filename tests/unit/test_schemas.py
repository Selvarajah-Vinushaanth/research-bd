"""
Unit tests for Pydantic schemas.
"""

import pytest
from pydantic import ValidationError


# =====================================================================
# User schemas
# =====================================================================

class TestUserSchemas:

    def test_user_register_valid(self):
        from app.schemas.user_schema import UserRegister

        user = UserRegister(
            email="test@example.com",
            password="StrongP@ss1",
            full_name="Test User",
        )
        assert user.email == "test@example.com"
        assert user.full_name == "Test User"

    def test_user_register_weak_password(self):
        from app.schemas.user_schema import UserRegister

        with pytest.raises(ValidationError):
            UserRegister(
                email="test@example.com",
                password="weak",
                full_name="Test User",
            )

    def test_user_register_invalid_email(self):
        from app.schemas.user_schema import UserRegister

        with pytest.raises(ValidationError):
            UserRegister(
                email="not-an-email",
                password="StrongP@ss1",
                full_name="Test User",
            )

    def test_user_login(self):
        from app.schemas.user_schema import UserLogin

        login = UserLogin(email="test@example.com", password="password123")
        assert login.email == "test@example.com"


# =====================================================================
# Paper schemas
# =====================================================================

class TestPaperSchemas:

    def test_paper_search_valid(self):
        from app.schemas.paper_schema import PaperSearch

        search = PaperSearch(query="transformer attention", top_k=5)
        assert search.query == "transformer attention"
        assert search.top_k == 5

    def test_paper_search_defaults(self):
        from app.schemas.paper_schema import PaperSearch

        search = PaperSearch(query="test")
        assert search.top_k == 10  # default

    def test_paper_update_partial(self):
        from app.schemas.paper_schema import PaperUpdate

        update = PaperUpdate(title="New Title")
        assert update.title == "New Title"
        assert update.tags is None


# =====================================================================
# Chat schemas
# =====================================================================

class TestChatSchemas:

    def test_chat_question_valid(self):
        from app.schemas.chat_schema import ChatQuestion

        q = ChatQuestion(
            question="What is attention mechanism?",
            paper_id="paper-123",
        )
        assert q.question == "What is attention mechanism?"

    def test_chat_question_too_long(self):
        from app.schemas.chat_schema import ChatQuestion

        with pytest.raises(ValidationError):
            ChatQuestion(
                question="x" * 3000,
                paper_id="paper-123",
            )


# =====================================================================
# Note schemas
# =====================================================================

class TestNoteSchemas:

    def test_note_create_valid(self):
        from app.schemas.note_schema import NoteCreate

        note = NoteCreate(
            title="My Note",
            content="Some insightful content here.",
            paper_id="paper-123",
        )
        assert note.title == "My Note"

    def test_note_create_empty_title(self):
        from app.schemas.note_schema import NoteCreate

        with pytest.raises(ValidationError):
            NoteCreate(
                title="",
                content="Content",
                paper_id="paper-123",
            )
