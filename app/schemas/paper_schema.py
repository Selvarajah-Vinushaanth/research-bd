# ============================================
# Pydantic Schemas - Paper
# ============================================

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class PaperUploadResponse(BaseModel):
    id: str
    title: str
    status: str
    message: str


class PaperResponse(BaseModel):
    id: str
    title: str
    authors: List[str]
    abstract: Optional[str]
    file_url: str
    doi: Optional[str]
    journal: Optional[str]
    publication_date: Optional[datetime]
    keywords: List[str]
    language: str
    page_count: Optional[int]
    status: str
    processing_progress: float
    uploaded_by: str
    created_at: datetime

    class Config:
        from_attributes = True


class PaperListResponse(BaseModel):
    papers: List[PaperResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class PaperDetailResponse(PaperResponse):
    chunk_count: Optional[int] = None
    summary: Optional[PaperSummaryResponse] = None
    metadata: Optional[PaperMetadataResponse] = None


class PaperSummaryResponse(BaseModel):
    id: str
    summary_type: str
    background: Optional[str]
    methodology: Optional[str]
    results: Optional[str]
    limitations: Optional[str]
    conclusions: Optional[str]
    full_summary: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class PaperMetadataResponse(BaseModel):
    raw_text_length: Optional[int]
    chunk_count: Optional[int]
    detected_language: Optional[str]
    detected_sections: List[str]
    figure_count: Optional[int]
    table_count: Optional[int]
    reference_count: Optional[int]
    extraction_quality: Optional[float]
    processing_time: Optional[float]

    class Config:
        from_attributes = True


class PaperSearchRequest(BaseModel):
    query: str = Field(..., min_length=3, max_length=500)
    top_k: int = Field(default=10, ge=1, le=50)
    paper_ids: Optional[List[str]] = None
    threshold: float = Field(default=0.5, ge=0.0, le=1.0)


class PaperSearchResult(BaseModel):
    paper_id: str
    paper_title: str
    chunk_text: str
    chunk_index: int
    similarity: float
    section: Optional[str]


class PaperSearchResponse(BaseModel):
    query: str
    results: List[PaperSearchResult]
    total_results: int


class PaperUpdateRequest(BaseModel):
    title: Optional[str] = None
    authors: Optional[List[str]] = None
    abstract: Optional[str] = None
    doi: Optional[str] = None
    journal: Optional[str] = None
    keywords: Optional[List[str]] = None


class CitationResponse(BaseModel):
    paper_id: str
    format: str
    citation_text: str

    class Config:
        from_attributes = True


class CitationRequest(BaseModel):
    format: str = Field(default="APA", pattern="^(APA|MLA|IEEE|CHICAGO|HARVARD|BIBTEX)$")


class PaperInsightResponse(BaseModel):
    id: str
    paper_id: str
    key_contributions: List[str]
    research_gaps: List[str]
    future_work: List[str]
    methodology_notes: List[str]
    strengths: List[str]
    weaknesses: List[str]
    created_at: datetime

    class Config:
        from_attributes = True


class TopicClusterResponse(BaseModel):
    id: str
    name: str
    description: Optional[str]
    keywords: List[str]
    paper_count: int

    class Config:
        from_attributes = True


class ClusterRunRequest(BaseModel):
    algorithm: str = Field(default="kmeans", pattern="^(kmeans|hdbscan)$")
    n_clusters: int = Field(default=5, ge=2, le=50)
    min_cluster_size: int = Field(default=3, ge=2)


class ClusterRunResponse(BaseModel):
    clusters: List[TopicClusterResponse]
    total_papers: int
    algorithm: str


class PaperComparisonRequest(BaseModel):
    paper_ids: List[str] = Field(..., min_length=2, max_length=10)


class PaperComparisonResponse(BaseModel):
    paper_a_id: str
    paper_b_id: str
    similarity_score: Optional[float]
    common_themes: List[str]
    differences: List[str]
    comparison_text: Optional[str]

    class Config:
        from_attributes = True


class RelatedPaperResponse(BaseModel):
    paper_id: str
    title: str
    similarity: float
    authors: List[str]
