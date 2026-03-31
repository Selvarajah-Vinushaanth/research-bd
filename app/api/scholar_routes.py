# ============================================
# API Routes - Google Scholar Integration
# ============================================

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from prisma import Json

from app.database.prisma_client import get_db
from app.middleware.auth import get_current_user
from app.schemas.scholar_schema import (
    ScholarAuthorSearchRequest,
    ScholarAuthorSearchResponse,
    ScholarCiteRequest,
    ScholarResultResponse,
    ScholarSavedItemResponse,
    ScholarSavedListResponse,
    ScholarSaveRequest,
    ScholarSearchHistoryResponse,
    ScholarSearchRequest,
    ScholarSearchResponse,
)
from app.services.scholar_service import get_scholar_service

logger = structlog.get_logger()
router = APIRouter()


# ──────────────────────────────────────
# Search Google Scholar
# ──────────────────────────────────────
@router.post("/search", response_model=ScholarSearchResponse)
async def search_scholar(
    body: ScholarSearchRequest,
    user=Depends(get_current_user),
):
    """Search Google Scholar for academic papers."""
    db = get_db()
    service = get_scholar_service()

    try:
        results = await service.search_papers(
            query=body.query,
            max_results=body.max_results,
        )
    except Exception as e:
        logger.error("scholar_search_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to fetch results from Google Scholar. Please try again later.",
        )

    # Persist search + results
    search_record = await db.scholarsearch.create(
        data={
            "user": {"connect": {"id": user.id}},
            "query": body.query,
            "result_count": len(results),
        }
    )

    scholar_results = []
    for r in results:
        record = await db.scholarresult.create(
            data={
                "search": {"connect": {"id": search_record.id}},
                "scholar_id": r.get("scholar_id"),
                "title": r["title"],
                "authors": r.get("authors", []),
                "abstract": r.get("abstract"),
                "publication_year": r.get("publication_year"),
                "journal": r.get("journal"),
                "citation_count": r.get("citation_count", 0),
                "url": r.get("url"),
                "pdf_url": r.get("pdf_url"),
                "doi": r.get("doi"),
                "source": "google_scholar",
                "raw_data": Json(r),
            }
        )
        scholar_results.append(
            ScholarResultResponse(
                id=record.id,
                scholar_id=record.scholar_id,
                title=record.title,
                authors=record.authors,
                abstract=record.abstract,
                publication_year=record.publication_year,
                journal=record.journal,
                citation_count=record.citation_count,
                url=record.url,
                pdf_url=record.pdf_url,
                doi=record.doi,
                source=record.source,
                created_at=record.created_at,
            )
        )

    logger.info("scholar_search_saved", user_id=user.id, query=body.query, count=len(scholar_results))

    return ScholarSearchResponse(
        search_id=search_record.id,
        query=body.query,
        results=scholar_results,
        result_count=len(scholar_results),
        created_at=search_record.created_at,
    )


# ──────────────────────────────────────
# Search History
# ──────────────────────────────────────
@router.get("/history", response_model=ScholarSearchHistoryResponse)
async def get_search_history(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=50),
    user=Depends(get_current_user),
):
    """Get the user's Google Scholar search history."""
    db = get_db()

    total = await db.scholarsearch.count(where={"user_id": user.id})
    searches = await db.scholarsearch.find_many(
        where={"user_id": user.id},
        order={"created_at": "desc"},
        skip=(page - 1) * page_size,
        take=page_size,
    )

    return ScholarSearchHistoryResponse(
        searches=[
            {
                "id": s.id,
                "query": s.query,
                "result_count": s.result_count,
                "created_at": s.created_at,
            }
            for s in searches
        ],
        total=total,
    )


# ──────────────────────────────────────
# Get Search Results (by search ID)
# ──────────────────────────────────────
@router.get("/search/{search_id}", response_model=ScholarSearchResponse)
async def get_search_results(
    search_id: str,
    user=Depends(get_current_user),
):
    """Get cached results for a previous search."""
    db = get_db()

    search = await db.scholarsearch.find_first(
        where={"id": search_id, "user_id": user.id},
        include={"results": True},
    )

    if not search:
        raise HTTPException(status_code=404, detail="Search not found")

    return ScholarSearchResponse(
        search_id=search.id,
        query=search.query,
        results=[
            ScholarResultResponse(
                id=r.id,
                scholar_id=r.scholar_id,
                title=r.title,
                authors=r.authors,
                abstract=r.abstract,
                publication_year=r.publication_year,
                journal=r.journal,
                citation_count=r.citation_count,
                url=r.url,
                pdf_url=r.pdf_url,
                doi=r.doi,
                source=r.source,
                created_at=r.created_at,
            )
            for r in search.results
        ],
        result_count=search.result_count,
        created_at=search.created_at,
    )


# ──────────────────────────────────────
# Save / Bookmark a Scholar Result
# ──────────────────────────────────────
@router.post("/save", response_model=ScholarSavedItemResponse)
async def save_scholar_result(
    body: ScholarSaveRequest,
    user=Depends(get_current_user),
):
    """Save/bookmark a Google Scholar result for later."""
    db = get_db()

    # Verify the result exists
    result = await db.scholarresult.find_unique(where={"id": body.scholar_result_id})
    if not result:
        raise HTTPException(status_code=404, detail="Scholar result not found")

    # Check for duplicate
    existing = await db.scholarsaveditem.find_first(
        where={
            "user_id": user.id,
            "scholar_result_id": body.scholar_result_id,
        }
    )
    if existing:
        raise HTTPException(status_code=409, detail="Already saved")

    saved = await db.scholarsaveditem.create(
        data={
            "user": {"connect": {"id": user.id}},
            "scholar_result": {"connect": {"id": body.scholar_result_id}},
            "notes": body.notes,
        },
        include={"scholar_result": True},
    )

    return ScholarSavedItemResponse(
        id=saved.id,
        scholar_result=ScholarResultResponse(
            id=saved.scholar_result.id,
            scholar_id=saved.scholar_result.scholar_id,
            title=saved.scholar_result.title,
            authors=saved.scholar_result.authors,
            abstract=saved.scholar_result.abstract,
            publication_year=saved.scholar_result.publication_year,
            journal=saved.scholar_result.journal,
            citation_count=saved.scholar_result.citation_count,
            url=saved.scholar_result.url,
            pdf_url=saved.scholar_result.pdf_url,
            doi=saved.scholar_result.doi,
            source=saved.scholar_result.source,
            created_at=saved.scholar_result.created_at,
        ),
        notes=saved.notes,
        is_imported=saved.is_imported,
        saved_at=saved.saved_at,
    )


# ──────────────────────────────────────
# List Saved Scholar Results
# ──────────────────────────────────────
@router.get("/saved", response_model=ScholarSavedListResponse)
async def list_saved_results(
    user=Depends(get_current_user),
):
    """List all saved/bookmarked Google Scholar results."""
    db = get_db()

    items = await db.scholarsaveditem.find_many(
        where={"user_id": user.id},
        include={"scholar_result": True},
        order={"saved_at": "desc"},
    )

    return ScholarSavedListResponse(
        items=[
            ScholarSavedItemResponse(
                id=item.id,
                scholar_result=ScholarResultResponse(
                    id=item.scholar_result.id,
                    scholar_id=item.scholar_result.scholar_id,
                    title=item.scholar_result.title,
                    authors=item.scholar_result.authors,
                    abstract=item.scholar_result.abstract,
                    publication_year=item.scholar_result.publication_year,
                    journal=item.scholar_result.journal,
                    citation_count=item.scholar_result.citation_count,
                    url=item.scholar_result.url,
                    pdf_url=item.scholar_result.pdf_url,
                    doi=item.scholar_result.doi,
                    source=item.scholar_result.source,
                    created_at=item.scholar_result.created_at,
                ),
                notes=item.notes,
                is_imported=item.is_imported,
                saved_at=item.saved_at,
            )
            for item in items
        ],
        total=len(items),
    )


# ──────────────────────────────────────
# Remove Saved Item
# ──────────────────────────────────────
@router.delete("/saved/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_saved_result(
    item_id: str,
    user=Depends(get_current_user),
):
    """Remove a saved Google Scholar result."""
    db = get_db()

    item = await db.scholarsaveditem.find_first(
        where={"id": item_id, "user_id": user.id}
    )
    if not item:
        raise HTTPException(status_code=404, detail="Saved item not found")

    await db.scholarsaveditem.delete(where={"id": item_id})


# ──────────────────────────────────────
# Delete Search History Entry
# ──────────────────────────────────────
@router.delete("/history/{search_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_search_history(
    search_id: str,
    user=Depends(get_current_user),
):
    """Delete a search from history (cascades to results)."""
    db = get_db()

    search = await db.scholarsearch.find_first(
        where={"id": search_id, "user_id": user.id}
    )
    if not search:
        raise HTTPException(status_code=404, detail="Search not found")

    await db.scholarsearch.delete(where={"id": search_id})


# ──────────────────────────────────────
# Search Authors on Google Scholar
# ──────────────────────────────────────
@router.post("/authors", response_model=ScholarAuthorSearchResponse)
async def search_authors(
    body: ScholarAuthorSearchRequest,
    user=Depends(get_current_user),
):
    """Search for authors on Google Scholar."""
    service = get_scholar_service()

    try:
        authors = await service.search_author(body.author_name)
    except Exception as e:
        logger.error("scholar_author_search_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to search authors on Google Scholar.",
        )

    return ScholarAuthorSearchResponse(
        authors=authors,
        total=len(authors),
    )
