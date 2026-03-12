# ============================================
# Pydantic Schemas - Notes
# ============================================

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class NoteCreateRequest(BaseModel):
    paper_id: Optional[str] = None
    title: str = Field(default="Untitled Note", max_length=200)
    content: str = Field(..., min_length=1)
    note_type: str = Field(default="MANUAL", pattern="^(MANUAL|AI_GENERATED|HIGHLIGHT|ANNOTATION)$")
    tags: List[str] = Field(default_factory=list)


class NoteUpdateRequest(BaseModel):
    title: Optional[str] = Field(None, max_length=200)
    content: Optional[str] = None
    tags: Optional[List[str]] = None
    is_pinned: Optional[bool] = None


class NoteResponse(BaseModel):
    id: str
    user_id: str
    paper_id: Optional[str]
    paper_title: Optional[str] = None
    title: str
    content: str
    note_type: str
    tags: List[str]
    is_pinned: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class NoteListResponse(BaseModel):
    notes: List[NoteResponse]
    total: int


class AIGenerateNoteRequest(BaseModel):
    paper_id: str
    note_type: str = Field(
        default="summary",
        pattern="^(summary|key_findings|methodology|critique|literature_review)$",
    )


class CollectionCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    is_public: bool = False


class CollectionUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    is_public: Optional[bool] = None


class CollectionResponse(BaseModel):
    id: str
    name: str
    description: Optional[str]
    is_public: bool
    paper_count: int = 0
    created_at: datetime

    class Config:
        from_attributes = True


class CollectionPaperResponse(BaseModel):
    id: str
    title: str
    authors: List[str]
    abstract: Optional[str] = None
    status: str
    keywords: List[str] = []
    created_at: datetime
    added_at: datetime

    class Config:
        from_attributes = True


class CollectionDetailResponse(BaseModel):
    id: str
    name: str
    description: Optional[str]
    is_public: bool
    paper_count: int = 0
    papers: List[CollectionPaperResponse] = []
    created_at: datetime

    class Config:
        from_attributes = True


class ReadingListAddRequest(BaseModel):
    paper_id: str
    priority: str = Field(default="MEDIUM", pattern="^(LOW|MEDIUM|HIGH|URGENT)$")
    notes: Optional[str] = None
    due_date: Optional[datetime] = None


class ReadingListUpdateRequest(BaseModel):
    status: Optional[str] = Field(None, pattern="^(UNREAD|READING|COMPLETED|SKIPPED)$")
    priority: Optional[str] = Field(None, pattern="^(LOW|MEDIUM|HIGH|URGENT)$")
    notes: Optional[str] = None


class ReadingListItemResponse(BaseModel):
    id: str
    paper_id: str
    paper_title: Optional[str] = None
    paper_authors: Optional[List[str]] = None
    paper_status: Optional[str] = None
    priority: str
    status: str
    notes: Optional[str]
    due_date: Optional[datetime]
    added_at: datetime

    class Config:
        from_attributes = True


class AnnotationCreateRequest(BaseModel):
    paper_id: str
    page_number: Optional[int] = None
    content: str
    highlight: Optional[str] = None
    color: str = "#FFFF00"
    position: Optional[dict] = None


class AnnotationResponse(BaseModel):
    id: str
    paper_id: str
    page_number: Optional[int]
    content: str
    highlight: Optional[str]
    color: str
    position: Optional[dict]
    created_at: datetime

    class Config:
        from_attributes = True
