# ============================================
# API Routes - Research Notes
# ============================================

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query

from app.database.prisma_client import get_db
from app.middleware.auth import get_current_user
from app.schemas.note_schema import (
    AIGenerateNoteRequest,
    NoteCreateRequest,
    NoteListResponse,
    NoteResponse,
    NoteUpdateRequest,
)

logger = structlog.get_logger()
router = APIRouter()


@router.post("/create", response_model=NoteResponse, status_code=201)
async def create_note(request: NoteCreateRequest, user=Depends(get_current_user)):
    """Create a new research note."""
    db = get_db()

    # Verify paper exists and belongs to the current user
    paper_title = None
    if request.paper_id:
        paper = await db.paper.find_unique(where={"id": request.paper_id})
        if not paper or paper.uploaded_by != user.id:
            raise HTTPException(status_code=404, detail="Paper not found")
        paper_title = paper.title

    note = await db.researchnote.create(
        data={
            "user_id": user.id,
            "paper_id": request.paper_id,
            "title": request.title,
            "content": request.content,
            "note_type": request.note_type,
            "tags": request.tags,
        }
    )

    return NoteResponse(
        id=note.id,
        user_id=note.user_id,
        paper_id=note.paper_id,
        paper_title=paper_title,
        title=note.title,
        content=note.content,
        note_type=note.note_type,
        tags=note.tags,
        is_pinned=note.is_pinned,
        created_at=note.created_at,
        updated_at=note.updated_at,
    )

    


@router.get("", response_model=NoteListResponse)
async def list_notes(
    paper_id: str = None,
    tag: str = None,
    pinned_only: bool = False,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user=Depends(get_current_user),
):
    """List research notes with filtering."""
    db = get_db()

    where_clause = {"user_id": user.id}
    if paper_id:
        where_clause["paper_id"] = paper_id
    if pinned_only:
        where_clause["is_pinned"] = True
    if tag:
        where_clause["tags"] = {"has": tag}

    total = await db.researchnote.count(where=where_clause)
    notes = await db.researchnote.find_many(
        where=where_clause,
        include={"paper": True},
        skip=(page - 1) * page_size,
        take=page_size,
        order={"updated_at": "desc"},
    )

    return NoteListResponse(
        notes=[
            NoteResponse(
                id=n.id,
                user_id=n.user_id,
                paper_id=n.paper_id,
                paper_title=n.paper.title if n.paper else None,
                title=n.title,
                content=n.content,
                note_type=n.note_type,
                tags=n.tags,
                is_pinned=n.is_pinned,
                created_at=n.created_at,
                updated_at=n.updated_at,
            )
            for n in notes
        ],
        total=total,
    )


@router.get("/{note_id}", response_model=NoteResponse)
async def get_note(note_id: str, user=Depends(get_current_user)):
    """Get a specific note."""
    db = get_db()

    note = await db.researchnote.find_unique(
        where={"id": note_id},
        include={"paper": True},
    )
    if not note or note.user_id != user.id:
        raise HTTPException(status_code=404, detail="Note not found")

    return NoteResponse(
        id=note.id,
        user_id=note.user_id,
        paper_id=note.paper_id,
        paper_title=note.paper.title if note.paper else None,
        title=note.title,
        content=note.content,
        note_type=note.note_type,
        tags=note.tags,
        is_pinned=note.is_pinned,
        created_at=note.created_at,
        updated_at=note.updated_at,
    )


@router.put("/{note_id}", response_model=NoteResponse)
async def update_note(
    note_id: str,
    request: NoteUpdateRequest,
    user=Depends(get_current_user),
):
    """Update a research note."""
    db = get_db()

    note = await db.researchnote.find_unique(where={"id": note_id})
    if not note or note.user_id != user.id:
        raise HTTPException(status_code=404, detail="Note not found")

    update_data = request.model_dump(exclude_unset=True)
    updated = await db.researchnote.update(
        where={"id": note_id},
        data=update_data,
        include={"paper": True},
    )

    return NoteResponse(
        id=updated.id,
        user_id=updated.user_id,
        paper_id=updated.paper_id,
        paper_title=updated.paper.title if updated.paper else None,
        title=updated.title,
        content=updated.content,
        note_type=updated.note_type,
        tags=updated.tags,
        is_pinned=updated.is_pinned,
        created_at=updated.created_at,
        updated_at=updated.updated_at,
    )


@router.delete("/{note_id}", status_code=204)
async def delete_note(note_id: str, user=Depends(get_current_user)):
    """Delete a research note."""
    db = get_db()

    note = await db.researchnote.find_unique(where={"id": note_id})
    if not note or note.user_id != user.id:
        raise HTTPException(status_code=404, detail="Note not found")

    await db.researchnote.delete(where={"id": note_id})


@router.post("/generate", response_model=NoteResponse)
async def generate_ai_note(request: AIGenerateNoteRequest, user=Depends(get_current_user)):
    """
    Generate an AI-powered research note for a paper.
    
    Note types:
    - summary: Overall paper summary
    - key_findings: Key findings and results
    - methodology: Methodology breakdown
    - critique: Critical analysis
    - literature_review: Connection to related work
    """
    db = get_db()

    paper = await db.paper.find_unique(where={"id": request.paper_id})
    if not paper or paper.uploaded_by != user.id:
        raise HTTPException(status_code=404, detail="Paper not found")

    # Get paper text
    chunks = await db.paperchunk.find_many(
        where={"paper_id": request.paper_id},
        order={"chunk_index": "asc"},
    )

    if not chunks:
        raise HTTPException(status_code=400, detail="Paper has not been processed")

    full_text = " ".join(c.chunk_text for c in chunks)

    # Generate note content based on type
    from app.ai_models.summarizer_model import get_summarizer_model

    summarizer = get_summarizer_model()

    note_titles = {
        "summary": f"Summary: {paper.title}",
        "key_findings": f"Key Findings: {paper.title}",
        "methodology": f"Methodology Notes: {paper.title}",
        "critique": f"Critical Analysis: {paper.title}",
        "literature_review": f"Literature Context: {paper.title}",
    }

    # Generate content
    content = summarizer.summarize_long_document(full_text, max_length=500)

    # Format as structured note
    formatted_content = f"# {note_titles.get(request.note_type, 'Research Note')}\n\n"
    formatted_content += f"**Paper:** {paper.title}\n"
    formatted_content += f"**Authors:** {', '.join(paper.authors)}\n\n"
    formatted_content += f"## {request.note_type.replace('_', ' ').title()}\n\n"
    formatted_content += content

    # Create note
    note = await db.researchnote.create(
        data={
            "user_id": user.id,
            "paper_id": request.paper_id,
            "title": note_titles.get(request.note_type, "AI Note"),
            "content": formatted_content,
            "note_type": "AI_GENERATED",
            "tags": [request.note_type, "ai-generated"],
        }
    )

    return NoteResponse(
        id=note.id,
        user_id=note.user_id,
        paper_id=note.paper_id,
        paper_title=paper.title,
        title=note.title,
        content=note.content,
        note_type=note.note_type,
        tags=note.tags,
        is_pinned=note.is_pinned,
        created_at=note.created_at,
        updated_at=note.updated_at,
    )
