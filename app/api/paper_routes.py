# ============================================
# API Routes - Paper Management
# ============================================

from __future__ import annotations

import math
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse

from app.config import settings
from app.database.prisma_client import get_db
from app.middleware.auth import get_current_user
from app.schemas.paper_schema import (
    CitationRequest,
    CitationResponse,
    PaperDetailResponse,
    PaperListResponse,
    PaperResponse,
    PaperSearchRequest,
    PaperSearchResponse,
    PaperUpdateRequest,
    PaperUploadResponse,
    RelatedPaperResponse,
)
from app.services.citation_service import get_citation_service
from app.services.embedding_service import get_embedding_service
from app.services.gcs_service import get_gcs_service
from app.services.pdf_service import PDFService

logger = structlog.get_logger()
router = APIRouter()


@router.post("/upload", response_model=PaperUploadResponse, status_code=status.HTTP_202_ACCEPTED)
async def upload_paper(
    file: UploadFile = File(...),
    user=Depends(get_current_user),
):
    """
    Upload a research paper PDF for processing.
    
    The paper will be processed asynchronously:
    1. Stored in cloud storage
    2. Text extracted
    3. Embeddings generated
    4. Metadata extracted
    """
    db = get_db()

    # Validate file type
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PDF files are accepted",
        )

    # Read file content
    file_content = await file.read()

    # Validate PDF
    is_valid, message = PDFService.validate_pdf(file_content)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=message,
        )

    # Check for duplicate (per user — different users can upload the same paper)
    file_hash = PDFService.compute_hash(file_content)
    existing = await db.paper.find_first(where={"file_hash": file_hash, "uploaded_by": user.id})
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"You have already uploaded this paper (ID: {existing.id})",
        )

    # Extract basic metadata from PDF
    pdf_service = PDFService()
    pdf_data = await pdf_service.extract_text(file_content)
    metadata = pdf_data["metadata"]

    # Upload PDF to Google Cloud Storage
    gcs_path = f"papers/{user.id}/{file_hash}.pdf"
    gcs = get_gcs_service()
    try:
        if gcs.is_available:
            import asyncio
            await asyncio.get_event_loop().run_in_executor(
                None, gcs.upload_file, file_content, gcs_path
            )
            file_url = gcs_path
            logger.info("pdf_uploaded_to_gcs", path=gcs_path)
        else:
            logger.warning("gcs_not_available_storing_path_only")
            file_url = gcs_path
    except Exception as e:
        logger.error("gcs_upload_failed", error=str(e))
        file_url = gcs_path

    # Create paper record
    paper = await db.paper.create(
        data={
            "title": metadata.get("title", file.filename.replace(".pdf", "")),
            "authors": metadata.get("authors", []),
            "abstract": metadata.get("abstract"),
            "file_url": file_url,
            "file_hash": file_hash,
            "doi": metadata.get("doi"),
            "keywords": metadata.get("keywords", []),
            "page_count": pdf_data.get("page_count"),
            "status": "PROCESSING",
            "uploaded_by": user.id,
        }
    )

    # Create metadata record
    await db.papermetadata.create(
        data={
            "paper_id": paper.id,
            "raw_text_length": pdf_data["statistics"]["text_length"],
            "detected_language": "en",
            "figure_count": pdf_data["statistics"]["figure_count"],
            "table_count": pdf_data["statistics"]["table_count"],
            "equation_count": pdf_data["statistics"]["equation_count"],
            "reference_count": pdf_data["statistics"]["reference_count"],
            "processing_time": pdf_data["processing_time"],
        }
    )

    # Trigger async processing (chunking + embeddings)
    try:
        from app.workers.tasks import process_paper_task
        from app.workers.celery_worker import celery_app
        import asyncio

        # Check if any Celery workers are actually running before queuing
        def _check_celery_workers():
            try:
                inspector = celery_app.control.inspect(timeout=2.0)
                ping_result = inspector.ping()
                return bool(ping_result)
            except Exception:
                return False

        workers_available = await asyncio.get_event_loop().run_in_executor(
            None, _check_celery_workers
        )

        if workers_available:
            # Use apply_async with queue="celery" (default) so the
            # solo dev worker always picks it up.  The custom queue
            # routing is only useful when you run dedicated workers
            # per queue in production.
            process_paper_task.apply_async(
                args=[paper.id, pdf_data["text"]],
                queue="celery",
            )
            logger.info("paper_processing_queued", paper_id=paper.id)
        else:
            logger.warning("no_celery_workers_detected_processing_sync")
            await _process_paper_sync(paper.id, pdf_data["text"])
    except Exception as e:
        # If Celery is not available, process synchronously
        logger.warning("celery_unavailable_processing_sync", error=str(e))
        await _process_paper_sync(paper.id, pdf_data["text"])

    # Refresh paper to get latest status after processing
    paper = await db.paper.find_unique(where={"id": paper.id})
    final_status = paper.status if paper else "PROCESSING"
    final_message = (
        "Paper uploaded and processed successfully"
        if final_status == "PROCESSED"
        else "Paper uploaded and processing started"
    )

    # Log activity
    await db.activitylog.create(
        data={
            "user_id": user.id,
            "action": "PAPER_UPLOADED",
            "resource": "paper",
            "resource_id": paper.id,
        }
    )

    return PaperUploadResponse(
        id=paper.id,
        title=paper.title,
        status=final_status,
        message=final_message,
    )


async def _process_paper_sync(paper_id: str, full_text: str):
    """Synchronous fallback for paper processing when Celery is unavailable."""
    from app.utils.chunking import get_chunker

    db = get_db()
    chunker = get_chunker()

    try:
        # Chunk text
        chunks = chunker.chunk_by_tokens(full_text)
        chunks = chunker.merge_small_chunks(chunks)

        # Generate and store embeddings
        embedding_service = get_embedding_service()
        stored = await embedding_service.generate_and_store_embeddings(paper_id, chunks)

        # Update paper status
        await db.paper.update(
            where={"id": paper_id},
            data={
                "status": "PROCESSED",
                "processing_progress": 1.0,
            },
        )

        # Update metadata
        await db.papermetadata.update(
            where={"paper_id": paper_id},
            data={"chunk_count": stored},
        )

        logger.info("paper_processed_sync", paper_id=paper_id, chunks=stored)

    except Exception as e:
        logger.error("paper_processing_failed", paper_id=paper_id, error=str(e))
        await db.paper.update(
            where={"id": paper_id},
            data={"status": "FAILED"},
        )


@router.get("", response_model=PaperListResponse)
async def list_papers(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
    status_filter: Optional[str] = Query(None, alias="status"),
    search: Optional[str] = None,
    user=Depends(get_current_user),
):
    """
    List the current user's papers with pagination and filtering.
    """
    db = get_db()

    # Map common aliases to valid PaperStatus enum values
    _STATUS_ALIASES = {
        "COMPLETED": "PROCESSED",
        "DONE": "PROCESSED",
        "QUEUED": "PENDING",
    }
    _VALID_STATUSES = {"PENDING", "PROCESSING", "PROCESSED", "FAILED", "ARCHIVED"}

    where_clause = {"uploaded_by": user.id}
    if status_filter:
        normalised = _STATUS_ALIASES.get(status_filter.upper(), status_filter.upper())
        if normalised in _VALID_STATUSES:
            where_clause["status"] = normalised
        # else: silently ignore invalid status (return all papers)
    if search:
        where_clause["OR"] = [
            {"title": {"contains": search, "mode": "insensitive"}},
            {"abstract": {"contains": search, "mode": "insensitive"}},
        ]

    total = await db.paper.count(where=where_clause)
    papers = await db.paper.find_many(
        where=where_clause,
        skip=(page - 1) * page_size,
        take=page_size,
        order={"created_at": "desc"},
    )

    return PaperListResponse(
        papers=[
            PaperResponse(
                id=p.id,
                title=p.title,
                authors=p.authors,
                abstract=p.abstract,
                file_url=p.file_url,
                doi=p.doi,
                journal=p.journal,
                publication_date=p.publication_date,
                keywords=p.keywords,
                language=p.language,
                page_count=p.page_count,
                status=p.status,
                processing_progress=p.processing_progress,
                uploaded_by=p.uploaded_by,
                created_at=p.created_at,
            )
            for p in papers
        ],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=math.ceil(total / page_size) if total > 0 else 0,
    )


@router.get("/{paper_id}", response_model=PaperDetailResponse)
async def get_paper(paper_id: str, user=Depends(get_current_user)):
    """Get detailed information about a specific paper."""
    db = get_db()

    paper = await db.paper.find_unique(
        where={"id": paper_id},
        include={
            "summaries": True,
            "metadata": True,
        },
    )

    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    if paper.uploaded_by != user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    # Get chunk count
    chunk_count = await db.paperchunk.count(where={"paper_id": paper_id})

    summary = None
    if paper.summaries:
        s = paper.summaries[0]
        from app.schemas.paper_schema import PaperSummaryResponse
        summary = PaperSummaryResponse(
            id=s.id,
            summary_type=s.summary_type,
            background=s.background,
            methodology=s.methodology,
            results=s.results,
            limitations=s.limitations,
            conclusions=s.conclusions,
            full_summary=s.full_summary,
            created_at=s.created_at,
        )

    metadata_resp = None
    if paper.metadata:
        from app.schemas.paper_schema import PaperMetadataResponse
        m = paper.metadata
        metadata_resp = PaperMetadataResponse(
            raw_text_length=m.raw_text_length,
            chunk_count=m.chunk_count,
            detected_language=m.detected_language,
            detected_sections=m.detected_sections,
            figure_count=m.figure_count,
            table_count=m.table_count,
            reference_count=m.reference_count,
            extraction_quality=m.extraction_quality,
            processing_time=m.processing_time,
        )

    return PaperDetailResponse(
        id=paper.id,
        title=paper.title,
        authors=paper.authors,
        abstract=paper.abstract,
        file_url=paper.file_url,
        doi=paper.doi,
        journal=paper.journal,
        publication_date=paper.publication_date,
        keywords=paper.keywords,
        language=paper.language,
        page_count=paper.page_count,
        status=paper.status,
        processing_progress=paper.processing_progress,
        uploaded_by=paper.uploaded_by,
        created_at=paper.created_at,
        chunk_count=chunk_count,
        summary=summary,
        metadata=metadata_resp,
    )


@router.put("/{paper_id}", response_model=PaperResponse)
async def update_paper(
    paper_id: str,
    request: PaperUpdateRequest,
    user=Depends(get_current_user),
):
    """Update paper metadata."""
    db = get_db()

    paper = await db.paper.find_unique(where={"id": paper_id})
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    if paper.uploaded_by != user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    update_data = request.model_dump(exclude_unset=True)
    updated = await db.paper.update(
        where={"id": paper_id},
        data=update_data,
    )

    return PaperResponse(
        id=updated.id,
        title=updated.title,
        authors=updated.authors,
        abstract=updated.abstract,
        file_url=updated.file_url,
        doi=updated.doi,
        journal=updated.journal,
        publication_date=updated.publication_date,
        keywords=updated.keywords,
        language=updated.language,
        page_count=updated.page_count,
        status=updated.status,
        processing_progress=updated.processing_progress,
        uploaded_by=updated.uploaded_by,
        created_at=updated.created_at,
    )


@router.delete("/{paper_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_paper(paper_id: str, user=Depends(get_current_user)):
    """Delete a paper and all associated data."""
    db = get_db()

    paper = await db.paper.find_unique(where={"id": paper_id})
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    if paper.uploaded_by != user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    # Also delete PDF from GCS
    gcs = get_gcs_service()
    if gcs.is_available and paper.file_url:
        try:
            import asyncio
            await asyncio.get_event_loop().run_in_executor(
                None, gcs.delete_file, paper.file_url
            )
        except Exception as e:
            logger.warning("gcs_delete_failed", error=str(e))

    await db.paper.delete(where={"id": paper_id})
    logger.info("paper_deleted", paper_id=paper_id, user_id=user.id)


@router.get("/{paper_id}/download")
async def download_paper_pdf(paper_id: str, user=Depends(get_current_user)):
    """
    Download the original PDF file for a paper.

    The backend fetches the PDF from GCS and streams it to the client.
    This keeps GCS credentials on the server side.
    """
    db = get_db()

    paper = await db.paper.find_unique(where={"id": paper_id})
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    if paper.uploaded_by != user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    if not paper.file_url:
        raise HTTPException(status_code=404, detail="No PDF file associated with this paper")

    gcs = get_gcs_service()
    if not gcs.is_available:
        raise HTTPException(
            status_code=503, detail="Cloud storage is not configured"
        )

    try:
        import asyncio
        import io

        pdf_bytes = await asyncio.get_event_loop().run_in_executor(
            None, gcs.download_file, paper.file_url
        )

        # Build a safe filename
        safe_title = "".join(
            c if c.isalnum() or c in (" ", "-", "_") else "_" for c in paper.title
        ).strip()[:100]
        filename = f"{safe_title}.pdf" if safe_title else "paper.pdf"

        return StreamingResponse(
            io.BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Content-Length": str(len(pdf_bytes)),
            },
        )
    except FileNotFoundError:
        raise HTTPException(
            status_code=404, detail="PDF file not found in cloud storage"
        )
    except Exception as e:
        logger.error("pdf_download_failed", paper_id=paper_id, error=str(e))
        raise HTTPException(
            status_code=500, detail="Failed to download PDF"
        )


@router.get("/{paper_id}/preview-url")
async def get_paper_preview_url(paper_id: str, user=Depends(get_current_user)):
    """
    Get a time-limited signed URL for previewing the PDF in the browser.

    The URL is valid for 60 minutes. Frontend can use this with an
    <iframe> or PDF.js viewer.
    """
    db = get_db()

    paper = await db.paper.find_unique(where={"id": paper_id})
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    if paper.uploaded_by != user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    if not paper.file_url:
        raise HTTPException(status_code=404, detail="No PDF file associated with this paper")

    gcs = get_gcs_service()
    if not gcs.is_available:
        raise HTTPException(
            status_code=503, detail="Cloud storage is not configured"
        )

    try:
        import asyncio

        signed_url = await asyncio.get_event_loop().run_in_executor(
            None, gcs.get_signed_url, paper.file_url, 60
        )
        return {"preview_url": signed_url, "expires_in_minutes": 60}
    except Exception as e:
        logger.error("preview_url_failed", paper_id=paper_id, error=str(e))
        raise HTTPException(
            status_code=500, detail="Failed to generate preview URL"
        )


@router.post("/{paper_id}/reprocess", status_code=status.HTTP_202_ACCEPTED)
async def reprocess_paper(paper_id: str, user=Depends(get_current_user)):
    """
    Reprocess a paper that is stuck in PROCESSING or FAILED state.
    Re-extracts text from the stored PDF and regenerates embeddings.
    """
    db = get_db()

    paper = await db.paper.find_unique(where={"id": paper_id})
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    if paper.uploaded_by != user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    if paper.status not in ("PROCESSING", "FAILED"):
        raise HTTPException(
            status_code=400,
            detail=f"Paper is already {paper.status}. Only PROCESSING or FAILED papers can be reprocessed.",
        )

    # Delete any existing chunks to start fresh
    await db.paperchunk.delete_many(where={"paper_id": paper_id})

    # Update status
    await db.paper.update(
        where={"id": paper_id},
        data={"status": "PROCESSING", "processing_progress": 0.0},
    )

    # Try to re-extract text from the stored PDF in GCS
    try:
        import asyncio
        pdf_service = PDFService()
        gcs = get_gcs_service()

        if gcs.is_available and paper.file_url:
            file_content = await asyncio.get_event_loop().run_in_executor(
                None, gcs.download_file, paper.file_url
            )
            pdf_data = await pdf_service.extract_text(file_content)
            full_text = pdf_data["text"]
        else:
            raise HTTPException(
                status_code=400,
                detail="PDF file not available. Please delete and re-upload the paper.",
            )

        await _process_paper_sync(paper_id, full_text)
        logger.info("paper_reprocessed", paper_id=paper_id)
        return {"message": "Paper reprocessed successfully", "paper_id": paper_id, "status": "PROCESSED"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("paper_reprocess_failed", paper_id=paper_id, error=str(e))
        await db.paper.update(
            where={"id": paper_id},
            data={"status": "FAILED"},
        )
        raise HTTPException(status_code=500, detail=f"Reprocessing failed: {str(e)}")


@router.post("/search", response_model=PaperSearchResponse)
async def search_papers(
    request: PaperSearchRequest,
    user=Depends(get_current_user),
):
    """
    Semantic search across paper chunks.
    Uses vector similarity to find relevant passages.
    """
    embedding_service = get_embedding_service()

    results = await embedding_service.semantic_search(
        query=request.query,
        top_k=request.top_k,
        paper_ids=request.paper_ids,
        threshold=request.threshold,
        user_id=user.id,
    )

    from app.schemas.paper_schema import PaperSearchResult
    return PaperSearchResponse(
        query=request.query,
        results=[
            PaperSearchResult(
                paper_id=r["paper_id"],
                paper_title=r["paper_title"],
                chunk_text=r["chunk_text"],
                chunk_index=r["chunk_index"],
                similarity=r["similarity"],
                section=r.get("section"),
            )
            for r in results
        ],
        total_results=len(results),
    )


@router.get("/{paper_id}/citation", response_model=CitationResponse)
async def get_citation(
    paper_id: str,
    format: str = Query(default="APA", regex="^(APA|MLA|IEEE|CHICAGO|HARVARD|BIBTEX)$"),
    user=Depends(get_current_user),
):
    """Generate a citation for a paper in the specified format."""
    db = get_db()
    paper = await db.paper.find_unique(where={"id": paper_id})
    if not paper or paper.uploaded_by != user.id:
        raise HTTPException(status_code=404, detail="Paper not found")

    citation_service = get_citation_service()
    result = await citation_service.generate_citation(paper_id, format)
    return CitationResponse(**result)


@router.get("/{paper_id}/citations")
async def get_all_citations(paper_id: str, user=Depends(get_current_user)):
    """Generate citations in all supported formats."""
    db = get_db()
    paper = await db.paper.find_unique(where={"id": paper_id})
    if not paper or paper.uploaded_by != user.id:
        raise HTTPException(status_code=404, detail="Paper not found")

    citation_service = get_citation_service()
    return await citation_service.generate_all_formats(paper_id)


@router.get("/{paper_id}/related", response_model=list[RelatedPaperResponse])
async def get_related_papers(
    paper_id: str,
    top_k: int = Query(default=10, ge=1, le=50),
    user=Depends(get_current_user),
):
    """Find papers related to a given paper using semantic similarity."""
    db = get_db()
    paper = await db.paper.find_unique(where={"id": paper_id})
    if not paper or paper.uploaded_by != user.id:
        raise HTTPException(status_code=404, detail="Paper not found")

    embedding_service = get_embedding_service()
    related = await embedding_service.find_related_papers(paper_id, top_k, user_id=user.id)
    return [RelatedPaperResponse(**r) for r in related]
