# ============================================
# API Routes - Chat (RAG Q&A)
# ============================================

from __future__ import annotations

import time
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from prisma import Json
from app.database.prisma_client import get_db
from app.middleware.auth import get_current_user
from app.schemas.chat_schema import (
    ChatAskRequest,
    ChatAskResponse,
    ChatHistoryResponse,
    ChatMessageFlat,
    ChatMessageResponse,
    ChatSessionResponse,
    ChatSourceChunk,
    MultiPaperChatRequest,
)
from app.services.rag_service import get_rag_service

logger = structlog.get_logger()
router = APIRouter()


@router.post("/ask", response_model=ChatAskResponse)
async def ask_question(request: ChatAskRequest, user=Depends(get_current_user)):
    """
    Ask a question about a research paper using RAG pipeline.
    
    Process:
    1. Embed the question
    2. Retrieve top-k relevant chunks from the paper
    3. Pass chunks as context to the QA model
    4. Return the answer with source citations
    """
    db = get_db()
    start_time = time.time()

    # Get or create chat session
    session_id = request.session_id
    if not session_id:
        paper_id = request.paper_id
        session = await db.chatsession.create(
            data={
                "user_id": user.id,
                "paper_id": paper_id,
                "title": request.question[:50] + "..." if len(request.question) > 50 else request.question,
                "session_type": "MULTI_PAPER" if request.paper_ids else "SINGLE_PAPER",
            }
        )
        session_id = session.id
    else:
        session = await db.chatsession.find_unique(where={"id": session_id})
        if not session or session.user_id != user.id:
            raise HTTPException(status_code=404, detail="Chat session not found")

    # Verify paper ownership before running RAG
    if request.paper_id:
        paper = await db.paper.find_unique(where={"id": request.paper_id})
        if not paper or paper.uploaded_by != user.id:
            raise HTTPException(status_code=404, detail="Paper not found")
    if request.paper_ids:
        for pid in request.paper_ids:
            paper = await db.paper.find_unique(where={"id": pid})
            if not paper or paper.uploaded_by != user.id:
                raise HTTPException(status_code=404, detail=f"Paper {pid} not found")

    # Run RAG pipeline
    rag_service = get_rag_service()
    result = await rag_service.ask(
        question=request.question,
        paper_id=request.paper_id,
        paper_ids=request.paper_ids,
        top_k=request.top_k,
        include_context=request.include_context,
        user_id=user.id,
    )

    # Store the message
    message = await db.chatmessage.create(
        data={
            "session_id": session_id,
            "role": "USER",
            "message": request.question,
            "response": result["answer"],
            "confidence": result.get("confidence"),
            "tokens_used": result.get("tokens_used"),
            "response_time": result.get("response_time"),
            "context_chunks": [s["chunk_text"][:200] for s in result.get("sources", [])[:5]],
        }
    )

    # Log activity
    await db.activitylog.create(
        data={
            "user_id": user.id,
            "action": "CHAT_QUESTION",
            "resource": "chat",
            "resource_id": session_id,
            "details": Json({"question_length": len(request.question)}),
        }
    )

    return ChatAskResponse(
        session_id=session_id,
        message_id=message.id,
        question=request.question,
        answer=result["answer"],
        confidence=result.get("confidence"),
        sources=[
            ChatSourceChunk(
                chunk_text=s["chunk_text"],
                paper_id=s["paper_id"],
                paper_title=s.get("paper_title", ""),
                chunk_index=s["chunk_index"],
                similarity=s["similarity"],
                section=s.get("section"),
            )
            for s in result.get("sources", [])
        ],
        tokens_used=result.get("tokens_used"),
        response_time=result.get("response_time", round(time.time() - start_time, 3)),
    )


@router.post("/multi-paper", response_model=ChatAskResponse)
async def multi_paper_chat(request: MultiPaperChatRequest, user=Depends(get_current_user)):
    """
    Ask a question across multiple papers simultaneously.
    Useful for comparative analysis and literature review.
    """
    ask_request = ChatAskRequest(
        question=request.question,
        paper_ids=request.paper_ids,
        session_id=request.session_id,
        top_k=request.top_k,
        include_context=True,
    )
    return await ask_question(ask_request, user)


@router.get("/sessions", response_model=list[ChatSessionResponse])
async def list_sessions(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user=Depends(get_current_user),
):
    """List all chat sessions for the current user."""
    db = get_db()

    sessions = await db.chatsession.find_many(
        where={"user_id": user.id},
        skip=(page - 1) * page_size,
        take=page_size,
        order={"updated_at": "desc"},
        include={"messages": True},
    )

    return [
        ChatSessionResponse(
            id=s.id,
            title=s.title,
            session_type=s.session_type,
            paper_id=s.paper_id,
            is_active=s.is_active,
            message_count=len(s.messages) if s.messages else 0,
            created_at=s.created_at,
            updated_at=s.updated_at,
        )
        for s in sessions
    ]


@router.get("/sessions/{session_id}", response_model=ChatHistoryResponse)
async def get_session_history(session_id: str, user=Depends(get_current_user)):
    """Get full chat history for a session."""
    db = get_db()

    session = await db.chatsession.find_unique(
        where={"id": session_id},
        include={"messages": {"order_by": {"created_at": "asc"}}},
    )

    if not session or session.user_id != user.id:
        raise HTTPException(status_code=404, detail="Session not found")

    return ChatHistoryResponse(
        session=ChatSessionResponse(
            id=session.id,
            title=session.title,
            session_type=session.session_type,
            paper_id=session.paper_id,
            is_active=session.is_active,
            message_count=len(session.messages) if session.messages else 0,
            created_at=session.created_at,
            updated_at=session.updated_at,
        ),
        messages=_flatten_messages(session.messages or []),
    )


def _flatten_messages(messages) -> list[ChatMessageFlat]:
    """
    Flatten ChatMessage records into separate user and assistant entries.

    Each DB row stores the user question in ``message`` and the AI answer in
    ``response``.  The frontend expects a flat list of alternating USER /
    ASSISTANT messages so it can render a normal chat timeline.
    """
    flat: list[ChatMessageFlat] = []
    for m in messages:
        # User message
        flat.append(
            ChatMessageFlat(
                id=f"{m.id}_user",
                role="USER",
                content=m.message,
                confidence=None,
                tokens_used=None,
                response_time=None,
                created_at=m.created_at,
            )
        )
        # Assistant message (if present)
        if m.response:
            flat.append(
                ChatMessageFlat(
                    id=f"{m.id}_assistant",
                    role="ASSISTANT",
                    content=m.response,
                    confidence=m.confidence,
                    tokens_used=m.tokens_used,
                    response_time=m.response_time,
                    created_at=m.created_at,
                )
            )
    return flat


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_session(session_id: str, user=Depends(get_current_user)):
    """Delete a chat session and all messages."""
    db = get_db()

    session = await db.chatsession.find_unique(where={"id": session_id})
    if not session or session.user_id != user.id:
        raise HTTPException(status_code=404, detail="Session not found")

    await db.chatsession.delete(where={"id": session_id})
    logger.info("chat_session_deleted", session_id=session_id)
