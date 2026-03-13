# ============================================
# API Routes - Collections & Reading List
# ============================================

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query

from app.database.prisma_client import get_db
from app.middleware.auth import get_current_user
from app.schemas.note_schema import (
    AnnotationCreateRequest,
    AnnotationResponse,
    CollectionCreateRequest,
    CollectionDetailResponse,
    CollectionPaperResponse,
    CollectionResponse,
    CollectionUpdateRequest,
    ReadingListAddRequest,
    ReadingListItemResponse,
    ReadingListUpdateRequest,
)

logger = structlog.get_logger()
router = APIRouter()


# ============================================
# Reading List  (MUST be defined BEFORE /{collection_id} routes
#               to avoid FastAPI matching "reading-list" as a
#               collection_id path parameter.)
# ============================================


@router.post("/reading-list", response_model=ReadingListItemResponse, status_code=201)
async def add_to_reading_list(request: ReadingListAddRequest, user=Depends(get_current_user)):
    """Add a paper to the reading list."""
    db = get_db()

    paper = await db.paper.find_unique(where={"id": request.paper_id})
    if not paper or paper.uploaded_by != user.id:
        raise HTTPException(status_code=404, detail="Paper not found")

    try:
        item = await db.readinglistitem.create(
            data={
                "user_id": user.id,
                "paper_id": request.paper_id,
                "priority": request.priority,
                "notes": request.notes,
                "due_date": request.due_date,
            }
        )
    except Exception:
        raise HTTPException(status_code=409, detail="Paper already in reading list")

    return ReadingListItemResponse(
        id=item.id,
        paper_id=item.paper_id,
        paper_title=paper.title,
        paper_authors=paper.authors,
        paper_status=paper.status,
        priority=item.priority,
        status=item.status,
        notes=item.notes,
        due_date=item.due_date,
        added_at=item.added_at,
    )


@router.get("/reading-list", response_model=list[ReadingListItemResponse])
async def get_reading_list(
    status: str = Query(None, alias="status"),
    priority: str = None,
    user=Depends(get_current_user),
):
    """Get the user's reading list with full paper details."""
    db = get_db()

    where_clause: dict = {"user_id": user.id}
    if status:
        where_clause["status"] = status
    if priority:
        where_clause["priority"] = priority

    items = await db.readinglistitem.find_many(
        where=where_clause,
        include={"paper": True},
        order={"added_at": "desc"},
    )

    return [
        ReadingListItemResponse(
            id=i.id,
            paper_id=i.paper_id,
            paper_title=i.paper.title if i.paper else None,
            paper_authors=i.paper.authors if i.paper else None,
            paper_status=i.paper.status if i.paper else None,
            priority=i.priority,
            status=i.status,
            notes=i.notes,
            due_date=i.due_date,
            added_at=i.added_at,
        )
        for i in items
    ]


@router.put("/reading-list/{item_id}", response_model=ReadingListItemResponse)
async def update_reading_list_item(
    item_id: str,
    request: ReadingListUpdateRequest,
    user=Depends(get_current_user),
):
    """Update a reading list item."""
    db = get_db()

    item = await db.readinglistitem.find_unique(where={"id": item_id})
    if not item or item.user_id != user.id:
        raise HTTPException(status_code=404, detail="Item not found")

    update_data = request.model_dump(exclude_unset=True)
    updated = await db.readinglistitem.update(
        where={"id": item_id},
        data=update_data,
        include={"paper": True},
    )

    return ReadingListItemResponse(
        id=updated.id,
        paper_id=updated.paper_id,
        paper_title=updated.paper.title if updated.paper else None,
        paper_authors=updated.paper.authors if updated.paper else None,
        paper_status=updated.paper.status if updated.paper else None,
        priority=updated.priority,
        status=updated.status,
        notes=updated.notes,
        due_date=updated.due_date,
        added_at=updated.added_at,
    )


@router.delete("/reading-list/{item_id}", status_code=204)
async def delete_reading_list_item(
    item_id: str,
    user=Depends(get_current_user),
):
    """Remove an item from the reading list."""
    db = get_db()

    item = await db.readinglistitem.find_unique(where={"id": item_id})
    if not item or item.user_id != user.id:
        raise HTTPException(status_code=404, detail="Item not found")

    await db.readinglistitem.delete(where={"id": item_id})


# ============================================
# Annotations  (Also before /{collection_id} to avoid conflicts)
# ============================================


@router.post("/annotations", response_model=AnnotationResponse, status_code=201)
async def create_annotation(request: AnnotationCreateRequest, user=Depends(get_current_user)):
    """Create a paper annotation."""
    db = get_db()

    annotation = await db.annotation.create(
        data={
            "user_id": user.id,
            "paper_id": request.paper_id,
            "page_number": request.page_number,
            "content": request.content,
            "highlight": request.highlight,
            "color": request.color,
            "position": request.position,
        }
    )

    return AnnotationResponse(
        id=annotation.id,
        paper_id=annotation.paper_id,
        page_number=annotation.page_number,
        content=annotation.content,
        highlight=annotation.highlight,
        color=annotation.color,
        position=annotation.position,
        created_at=annotation.created_at,
    )


@router.get("/annotations/{paper_id}", response_model=list[AnnotationResponse])
async def get_annotations(paper_id: str, user=Depends(get_current_user)):
    """Get annotations for a paper."""
    db = get_db()

    annotations = await db.annotation.find_many(
        where={"paper_id": paper_id, "user_id": user.id},
        order={"page_number": "asc"},
    )

    return [
        AnnotationResponse(
            id=a.id,
            paper_id=a.paper_id,
            page_number=a.page_number,
            content=a.content,
            highlight=a.highlight,
            color=a.color,
            position=a.position,
            created_at=a.created_at,
        )
        for a in annotations
    ]


@router.delete("/annotations/{annotation_id}", status_code=204)
async def delete_annotation(annotation_id: str, user=Depends(get_current_user)):
    """Delete an annotation."""
    db = get_db()

    annotation = await db.annotation.find_unique(where={"id": annotation_id})
    if not annotation or annotation.user_id != user.id:
        raise HTTPException(status_code=404, detail="Annotation not found")

    await db.annotation.delete(where={"id": annotation_id})


# ============================================
# Collections
# ============================================


@router.post("", response_model=CollectionResponse, status_code=201)
async def create_collection(request: CollectionCreateRequest, user=Depends(get_current_user)):
    """Create a new paper collection."""
    db = get_db()

    collection = await db.collection.create(
        data={
            "user_id": user.id,
            "name": request.name,
            "description": request.description,
            "is_public": request.is_public,
        }
    )

    return CollectionResponse(
        id=collection.id,
        name=collection.name,
        description=collection.description,
        is_public=collection.is_public,
        paper_count=0,
        created_at=collection.created_at,
    )


@router.get("", response_model=list[CollectionResponse])
async def list_collections(user=Depends(get_current_user)):
    """List all collections for the current user."""
    db = get_db()

    collections = await db.collection.find_many(
        where={"user_id": user.id},
        include={"items": True},
        order={"created_at": "desc"},
    )

    return [
        CollectionResponse(
            id=c.id,
            name=c.name,
            description=c.description,
            is_public=c.is_public,
            paper_count=len(c.items) if c.items else 0,
            created_at=c.created_at,
        )
        for c in collections
    ]


@router.put("/{collection_id}", response_model=CollectionResponse)
async def update_collection(
    collection_id: str,
    request: CollectionUpdateRequest,
    user=Depends(get_current_user),
):
    """Update a collection."""
    db = get_db()

    collection = await db.collection.find_unique(where={"id": collection_id})
    if not collection or collection.user_id != user.id:
        raise HTTPException(status_code=404, detail="Collection not found")

    update_data = request.model_dump(exclude_unset=True)
    updated = await db.collection.update(
        where={"id": collection_id},
        data=update_data,
        include={"items": True},
    )

    return CollectionResponse(
        id=updated.id,
        name=updated.name,
        description=updated.description,
        is_public=updated.is_public,
        paper_count=len(updated.items) if updated.items else 0,
        created_at=updated.created_at,
    )


@router.get("/{collection_id}", response_model=CollectionDetailResponse)
async def get_collection_detail(
    collection_id: str,
    user=Depends(get_current_user),
):
    """Get a collection with all its papers."""
    db = get_db()

    collection = await db.collection.find_unique(
        where={"id": collection_id},
        include={"items": True},
    )

    if not collection or collection.user_id != user.id:
        raise HTTPException(status_code=404, detail="Collection not found")

    # Fetch full paper details for each item
    papers = []
    for item in (collection.items or []):
        paper = await db.paper.find_unique(where={"id": item.paper_id})
        if paper:
            papers.append(
                CollectionPaperResponse(
                    id=paper.id,
                    title=paper.title,
                    authors=paper.authors,
                    abstract=paper.abstract,
                    status=paper.status,
                    keywords=paper.keywords,
                    created_at=paper.created_at,
                    added_at=item.added_at,
                )
            )

    return CollectionDetailResponse(
        id=collection.id,
        name=collection.name,
        description=collection.description,
        is_public=collection.is_public,
        paper_count=len(papers),
        papers=papers,
        created_at=collection.created_at,
    )


@router.post("/{collection_id}/papers/{paper_id}", status_code=201)
async def add_paper_to_collection(
    collection_id: str,
    paper_id: str,
    user=Depends(get_current_user),
):
    """Add a paper to a collection."""
    db = get_db()

    collection = await db.collection.find_unique(where={"id": collection_id})
    if not collection or collection.user_id != user.id:
        raise HTTPException(status_code=404, detail="Collection not found")

    paper = await db.paper.find_unique(where={"id": paper_id})
    if not paper or paper.uploaded_by != user.id:
        raise HTTPException(status_code=404, detail="Paper not found")

    try:
        await db.collectionitem.create(
            data={
                "collection_id": collection_id,
                "paper_id": paper_id,
            }
        )
    except Exception:
        raise HTTPException(status_code=409, detail="Paper already in collection")

    return {"message": "Paper added to collection"}


@router.delete("/{collection_id}/papers/{paper_id}", status_code=204)
async def remove_paper_from_collection(
    collection_id: str,
    paper_id: str,
    user=Depends(get_current_user),
):
    """Remove a paper from a collection."""
    db = get_db()

    collection = await db.collection.find_unique(where={"id": collection_id})
    if not collection or collection.user_id != user.id:
        raise HTTPException(status_code=404, detail="Collection not found")

    await db.collectionitem.delete_many(
        where={"collection_id": collection_id, "paper_id": paper_id},
    )


@router.delete("/{collection_id}", status_code=204)
async def delete_collection(collection_id: str, user=Depends(get_current_user)):
    """Delete a collection."""
    db = get_db()

    collection = await db.collection.find_unique(where={"id": collection_id})
    if not collection or collection.user_id != user.id:
        raise HTTPException(status_code=404, detail="Collection not found")

    await db.collection.delete(where={"id": collection_id})
