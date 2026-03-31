# ============================================
# Pydantic Schemas - Google Scholar
# ============================================

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# --- Request Schemas ---

class ScholarSearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500, description="Search query for Google Scholar")
    max_results: int = Field(default=10, ge=1, le=20, description="Number of results to return")


class ScholarSaveRequest(BaseModel):
    scholar_result_id: str = Field(..., description="ID of the scholar result to save")
    notes: Optional[str] = Field(None, max_length=2000, description="Optional notes")


class ScholarCiteRequest(BaseModel):
    scholar_result_id: str = Field(..., description="ID of the scholar result")


class ScholarAuthorSearchRequest(BaseModel):
    author_name: str = Field(..., min_length=1, max_length=200, description="Author name to search")


# --- Response Schemas ---

class ScholarResultResponse(BaseModel):
    id: str
    scholar_id: Optional[str]
    title: str
    authors: List[str]
    abstract: Optional[str]
    publication_year: Optional[int]
    journal: Optional[str]
    citation_count: int
    url: Optional[str]
    pdf_url: Optional[str]
    doi: Optional[str]
    source: str
    created_at: datetime

    class Config:
        from_attributes = True


class ScholarSearchResponse(BaseModel):
    search_id: str
    query: str
    results: List[ScholarResultResponse]
    result_count: int
    created_at: datetime


class ScholarSearchHistoryItem(BaseModel):
    id: str
    query: str
    result_count: int
    created_at: datetime

    class Config:
        from_attributes = True


class ScholarSearchHistoryResponse(BaseModel):
    searches: List[ScholarSearchHistoryItem]
    total: int


class ScholarSavedItemResponse(BaseModel):
    id: str
    scholar_result: ScholarResultResponse
    notes: Optional[str]
    is_imported: bool
    saved_at: datetime

    class Config:
        from_attributes = True


class ScholarSavedListResponse(BaseModel):
    items: List[ScholarSavedItemResponse]
    total: int


class ScholarAuthorResponse(BaseModel):
    name: str
    affiliation: Optional[str]
    interests: List[str]
    citation_count: int
    h_index: Optional[int]
    i10_index: Optional[int]
    scholar_id: Optional[str]
    url: Optional[str]
    thumbnail: Optional[str]


class ScholarAuthorSearchResponse(BaseModel):
    authors: List[ScholarAuthorResponse]
    total: int
