# ============================================
# Pydantic Schemas - Chat
# ============================================

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class ChatAskRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=2000)
    paper_id: Optional[str] = None
    paper_ids: Optional[List[str]] = None
    session_id: Optional[str] = None
    top_k: int = Field(default=5, ge=1, le=20)
    include_context: bool = True


class ChatSourceChunk(BaseModel):
    chunk_text: str
    paper_id: str
    paper_title: str
    chunk_index: int
    similarity: float
    section: Optional[str]


class ChatAskResponse(BaseModel):
    session_id: str
    message_id: str
    question: str
    answer: str
    confidence: Optional[float]
    sources: List[ChatSourceChunk]
    tokens_used: Optional[int]
    response_time: float


class ChatSessionResponse(BaseModel):
    id: str
    title: str
    session_type: str
    paper_id: Optional[str]
    is_active: bool
    message_count: int = 0
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ChatMessageResponse(BaseModel):
    id: str
    role: str
    message: str
    response: Optional[str]
    confidence: Optional[float]
    tokens_used: Optional[int]
    response_time: Optional[float]
    created_at: datetime

    class Config:
        from_attributes = True


class ChatMessageFlat(BaseModel):
    """A single message (user or assistant) for flat chat display."""
    id: str
    role: str  # "USER" or "ASSISTANT"
    content: str
    confidence: Optional[float] = None
    tokens_used: Optional[int] = None
    response_time: Optional[float] = None
    created_at: datetime

    class Config:
        from_attributes = True


class ChatHistoryResponse(BaseModel):
    session: ChatSessionResponse
    messages: List[ChatMessageFlat]


class MultiPaperChatRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=2000)
    paper_ids: List[str] = Field(..., min_length=1, max_length=20)
    session_id: Optional[str] = None
    top_k: int = Field(default=5, ge=1, le=20)
