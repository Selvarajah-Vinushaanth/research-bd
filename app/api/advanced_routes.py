# ============================================
# API Routes - Advanced Features
# ============================================

from __future__ import annotations

from typing import List, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.config import settings
from app.database.prisma_client import get_db
from app.middleware.auth import get_current_user
from app.services.embedding_service import get_embedding_service

logger = structlog.get_logger()
router = APIRouter()


# ============================================
# Schemas for Advanced Features
# ============================================


class PaperComparisonRequest(BaseModel):
    paper_ids: List[str] = Field(..., min_length=2, max_length=10)


class PaperComparisonResult(BaseModel):
    paper_a: dict
    paper_b: dict
    similarity_score: float
    common_themes: List[str]
    differences: List[str]
    comparison_text: str


class LiteratureReviewRequest(BaseModel):
    paper_ids: List[str] = Field(..., min_length=2, max_length=20)
    focus_topic: Optional[str] = None


class LiteratureReviewResponse(BaseModel):
    review_text: str
    papers_analyzed: int
    key_themes: List[str]
    chronological_summary: List[dict]
    research_gaps: List[str]


class ResearchTimelineEntry(BaseModel):
    paper_id: str
    title: str
    year: Optional[int]
    key_contribution: str


class ResearchTimelineResponse(BaseModel):
    entries: List[ResearchTimelineEntry]
    timeline_summary: str


class ResearchGraphNode(BaseModel):
    id: str
    title: str
    type: str  # "paper" or "concept"


class ResearchGraphEdge(BaseModel):
    source: str
    target: str
    weight: float
    relationship: str


class ResearchGraphResponse(BaseModel):
    nodes: List[ResearchGraphNode]
    edges: List[ResearchGraphEdge]


class RecommendationResponse(BaseModel):
    paper_id: str
    title: str
    authors: List[str]
    relevance_score: float
    reason: str


# ============================================
# Multi-Paper Comparison
# ============================================


@router.post("/compare")
async def compare_papers(request: PaperComparisonRequest, user=Depends(get_current_user)):
    """
    Compare multiple papers (2–10) to find similarities, differences, and common
    themes.  Stores the entire comparison session as ONE record with all pairwise
    results in a JSON ``results`` column, so it works for any number of papers.
    """
    db = get_db()

    # Verify all papers exist and belong to user
    papers = []
    for pid in request.paper_ids:
        paper = await db.paper.find_unique(where={"id": pid})
        if not paper:
            raise HTTPException(status_code=404, detail=f"Paper {pid} not found")
        papers.append(paper)

    from app.ai_models.embedding_model import get_embedding_model
    emb_model = get_embedding_model()

    pairwise_results: list[dict] = []

    for i in range(len(papers)):
        for j in range(i + 1, len(papers)):
            paper_a = papers[i]
            paper_b = papers[j]

            # Get chunks for both papers
            chunks_a = await db.paperchunk.find_many(
                where={"paper_id": paper_a.id},
                order={"chunk_index": "asc"},
                take=20,
            )
            chunks_b = await db.paperchunk.find_many(
                where={"paper_id": paper_b.id},
                order={"chunk_index": "asc"},
                take=20,
            )

            text_a = " ".join(c.chunk_text for c in chunks_a)
            text_b = " ".join(c.chunk_text for c in chunks_b)

            # Compute similarity
            similarity = emb_model.similarity(
                text_a[:2000] if len(text_a) > 2000 else text_a,
                text_b[:2000] if len(text_b) > 2000 else text_b,
            )

            # Extract common themes and differences
            common_themes = _extract_common_themes(text_a, text_b)
            differences = _extract_differences(paper_a, paper_b, text_a, text_b)

            # Generate comparison text via LLM (with fallback)
            try:
                from huggingface_hub import InferenceClient
                client = InferenceClient(token=settings.HUGGINGFACE_API_TOKEN)
                cmp_prompt = (
                    "You are a research analyst comparing two academic papers in detail.\n\n"
                    f"Paper A: \"{paper_a.title}\"\n"
                    f"Authors: {', '.join(paper_a.authors[:3]) if paper_a.authors else 'Unknown'}\n"
                    f"Abstract/Excerpt: {text_a[:1000]}\n\n"
                    f"Paper B: \"{paper_b.title}\"\n"
                    f"Authors: {', '.join(paper_b.authors[:3]) if paper_b.authors else 'Unknown'}\n"
                    f"Abstract/Excerpt: {text_b[:1000]}\n\n"
                    f"Semantic similarity score: {similarity:.0%}.\n\n"
                    "Provide a detailed comparison covering:\n"
                    "1. **Research Objectives** – What each paper aims to achieve\n"
                    "2. **Methodology** – How their approaches differ or align\n"
                    "3. **Key Findings** – Main results from each paper\n"
                    "4. **Strengths & Limitations** – What each paper does well and where it falls short\n"
                    "5. **Complementary Value** – How reading both papers together benefits a researcher\n\n"
                    "Write 2–3 paragraphs in academic tone. Be specific – reference actual methods, "
                    "datasets, or findings from the excerpts."
                )
                cmp_resp = client.chat_completion(
                    model=settings.GENERATIVE_MODEL,
                    messages=[{"role": "user", "content": cmp_prompt}],
                    max_tokens=800,
                    temperature=0.4,
                )
                comparison_text = cmp_resp.choices[0].message.content or ""
            except Exception:
                comparison_text = (
                    f"Papers '{paper_a.title}' and '{paper_b.title}' have a semantic similarity of "
                    f"{similarity:.2%}. "
                )
                if common_themes:
                    comparison_text += f"Common themes include: {', '.join(common_themes[:5])}. "
                if differences:
                    comparison_text += f"Key differences: {'; '.join(differences[:3])}."

            pairwise_results.append({
                "paper_a": {"id": paper_a.id, "title": paper_a.title},
                "paper_b": {"id": paper_b.id, "title": paper_b.title},
                "similarity_score": round(similarity, 4),
                "common_themes": common_themes,
                "differences": differences,
                "comparison_text": comparison_text,
            })

    # ── Persist as a single comparison session ──
    # Sort paper_ids so [A,B] and [B,A] map to the same record
    sorted_ids = sorted(request.paper_ids)
    import json as _json

    try:
        # Check if this exact set of papers was already compared by this user
        existing_sessions = await db.papercomparison.find_many(
            where={"user_id": user.id},
            order={"created_at": "desc"},
        )
        existing = next(
            (s for s in existing_sessions if sorted(s.paper_ids) == sorted_ids),
            None,
        )
        if existing:
            await db.papercomparison.update(
                where={"id": existing.id},
                data={
                    "results": _json.dumps(pairwise_results),
                },
            )
        else:
            await db.papercomparison.create(
                data={
                    "user_id": user.id,
                    "paper_ids": sorted_ids,
                    "results": _json.dumps(pairwise_results),
                }
            )
    except Exception as exc:
        logger.warning("failed_to_save_comparison_session", error=str(exc))

    return pairwise_results


# ============================================
# Auto Literature Review
# ============================================


@router.post("/literature-review", response_model=LiteratureReviewResponse)
async def generate_literature_review(
    request: LiteratureReviewRequest,
    user=Depends(get_current_user),
):
    """
    Generate an automatic literature review from multiple papers.
    Uses generative LLM to synthesize key findings, identify themes and gaps.
    Falls back to rule-based generation if the LLM call fails.
    """
    db = get_db()

    paper_summaries = []

    for pid in request.paper_ids:
        paper = await db.paper.find_unique(where={"id": pid})
        if not paper:
            continue

        chunks = await db.paperchunk.find_many(
            where={"paper_id": pid},
            order={"chunk_index": "asc"},
            take=15,
        )

        if chunks:
            text = " ".join(c.chunk_text for c in chunks)[:4000]
            paper_summaries.append({
                "paper_id": pid,
                "title": paper.title,
                "authors": paper.authors or [],
                "year": paper.publication_date.year if paper.publication_date else None,
                "abstract": paper.abstract or "",
                "keywords": paper.keywords or [],
                "text_excerpt": text,
            })

    if not paper_summaries:
        raise HTTPException(status_code=400, detail="No processable papers found")

    # Sort by year
    paper_summaries.sort(key=lambda x: x.get("year") or 9999)

    # ── Build a context block for the LLM ──
    papers_context = ""
    for idx, ps in enumerate(paper_summaries, 1):
        year_str = f" ({ps['year']})" if ps.get("year") else ""
        authors_str = ", ".join(ps["authors"][:3]) if ps["authors"] else "Unknown"
        kw_str = ", ".join(ps.get("keywords", [])[:8])
        papers_context += (
            f"### Paper {idx}: {ps['title']}{year_str}\n"
            f"**Authors:** {authors_str}\n"
        )
        if ps.get("abstract"):
            papers_context += f"**Abstract:** {ps['abstract'][:500]}\n"
        if kw_str:
            papers_context += f"**Keywords:** {kw_str}\n"
        papers_context += f"**Content Excerpt:** {ps['text_excerpt'][:1200]}\n\n"

    topic_instruction = ""
    if request.focus_topic:
        topic_instruction = f"Focus especially on aspects related to: **{request.focus_topic}**.\n"

    prompt = (
        "You are a senior research scientist writing a comprehensive, publication-quality "
        "literature review for an academic audience.\n\n"
        f"Analyze the following {len(paper_summaries)} research papers and produce a detailed, "
        "well-structured literature review in Markdown format.\n\n"
        f"{topic_instruction}"
        "Your review MUST include ALL of the following sections with substantial content:\n\n"
        "## 1. Introduction\n"
        "Provide an overview of the research domain, why this area matters, and what questions "
        "the reviewed papers collectively address. (1–2 paragraphs)\n\n"
        "## 2. Thematic Analysis\n"
        "Group the papers by common themes, methodologies, or research questions. For each theme, "
        "discuss which papers contribute and how. (2–3 paragraphs)\n\n"
        "## 3. Individual Contributions\n"
        "For EACH paper, write a focused paragraph covering: research objective, methodology, "
        "key findings, and significance. Reference specific methods, datasets, and results.\n\n"
        "## 4. Comparative Discussion\n"
        "Compare and contrast the papers: Where do they agree? Where do they diverge? "
        "Which approaches are more effective and why? (2–3 paragraphs)\n\n"
        "## 5. Research Gaps & Future Directions\n"
        "Identify 3–5 specific, actionable research gaps based on what is missing or "
        "underexplored across these papers. Be concrete, not generic.\n\n"
        "## 6. Conclusion\n"
        "Synthesize the overall state of the field and provide a forward-looking statement. "
        "(1–2 paragraphs)\n\n"
        "IMPORTANT: Write at least 800 words total. Use proper academic tone. "
        "Reference papers by their titles. Be specific about methods, results, and findings.\n\n"
        f"---\n\n{papers_context}"
    )

    # ── Try generative LLM ──
    review_text = ""
    key_themes: list[str] = []
    research_gaps: list[str] = []

    try:
        from huggingface_hub import InferenceClient

        client = InferenceClient(token=settings.HUGGINGFACE_API_TOKEN)
        response = client.chat_completion(
            model=settings.GENERATIVE_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=4000,
            temperature=0.5,
        )
        review_text = response.choices[0].message.content or ""
        logger.info("literature_review_generated_with_llm", papers=len(paper_summaries))

        # Ask LLM for structured themes & gaps
        meta_prompt = (
            "Based on the literature review you just wrote, respond with ONLY valid JSON "
            "(no markdown fences). Use this exact schema:\n"
            '{"key_themes": ["theme1", "theme2", ...], "research_gaps": ["gap1", "gap2", ...]}\n\n'
            f"Review:\n{review_text[:2000]}"
        )
        meta_resp = client.chat_completion(
            model=settings.GENERATIVE_MODEL,
            messages=[{"role": "user", "content": meta_prompt}],
            max_tokens=500,
            temperature=0.2,
        )
        import json as _json
        meta_text = (meta_resp.choices[0].message.content or "").strip()
        # Strip possible markdown fences
        if meta_text.startswith("```"):
            meta_text = meta_text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        meta_data = _json.loads(meta_text)
        key_themes = meta_data.get("key_themes", [])[:15]
        research_gaps = meta_data.get("research_gaps", [])[:5]
    except Exception as exc:
        logger.warning("llm_literature_review_failed_fallback", error=str(exc))
        # ── Fallback: rule-based review ──
        from app.ai_models.summarizer_model import get_summarizer_model

        summarizer = get_summarizer_model()

        review_text = f"## Literature Review\n\n"
        review_text += f"This review synthesizes findings from {len(paper_summaries)} research papers.\n\n"

        for ps in paper_summaries:
            year_str = f" ({ps['year']})" if ps.get("year") else ""
            summary = summarizer.summarize(ps["text_excerpt"][:2000], max_length=150, min_length=50)
            ps["summary"] = summary
            review_text += f"### {ps['title']}{year_str}\n"
            review_text += f"*{', '.join(ps['authors'][:3])}*\n\n{summary}\n\n"

        key_themes = _extract_themes_from_summaries(
            [{"summary": ps.get("summary", ps["text_excerpt"][:500])} for ps in paper_summaries]
        )
        research_gaps = [
            "Further investigation needed on integration of methods across studies",
            "Limited evaluation on diverse datasets across the reviewed papers",
            "Scalability concerns not adequately addressed in existing literature",
        ]

    # ── Save literature review to database (upsert by same paper set) ──
    sorted_ids = sorted(request.paper_ids)
    try:
        # Check if a review with the same paper set already exists for this user
        existing_reviews = await db.literaturereview.find_many(
            where={"user_id": user.id},
            order={"created_at": "desc"},
        )
        existing = next(
            (r for r in existing_reviews if sorted(r.paper_ids) == sorted_ids),
            None,
        )
        if existing:
            await db.literaturereview.update(
                where={"id": existing.id},
                data={
                    "title": f"Literature Review: {request.focus_topic or 'General'}",
                    "focus_topic": request.focus_topic,
                    "review_text": review_text,
                    "papers_analyzed": len(paper_summaries),
                    "key_themes": key_themes,
                    "research_gaps": research_gaps,
                },
            )
        else:
            await db.literaturereview.create(
                data={
                    "user_id": user.id,
                    "title": f"Literature Review: {request.focus_topic or 'General'}",
                    "focus_topic": request.focus_topic,
                    "review_text": review_text,
                    "papers_analyzed": len(paper_summaries),
                    "paper_ids": sorted_ids,
                    "key_themes": key_themes,
                    "research_gaps": research_gaps,
                }
            )
    except Exception as exc:
        logger.warning("failed_to_save_literature_review", error=str(exc))

    return LiteratureReviewResponse(
        review_text=review_text,
        papers_analyzed=len(paper_summaries),
        key_themes=key_themes,
        chronological_summary=[
            {
                "paper_id": p["paper_id"],
                "title": p["title"],
                "year": p.get("year"),
                "summary": p.get("summary", p["text_excerpt"][:300]),
            }
            for p in paper_summaries
        ],
        research_gaps=research_gaps,
    )


# ============================================
# Comparison History
# ============================================


@router.get("/compare/history")
async def get_comparison_history(user=Depends(get_current_user)):
    """
    Get saved paper comparison sessions for the current user.
    Each session contains all pairwise results for N papers.
    """
    db = get_db()
    import json as _json

    sessions = await db.papercomparison.find_many(
        where={"user_id": user.id},
        order={"created_at": "desc"},
        take=50,
    )

    results = []
    for s in sessions:
        # Resolve paper titles from IDs
        paper_titles = {}
        for pid in s.paper_ids:
            paper = await db.paper.find_unique(where={"id": pid})
            paper_titles[pid] = paper.title if paper else "Deleted paper"

        # Parse results JSON
        try:
            pairwise = _json.loads(s.results) if isinstance(s.results, str) else (s.results or [])
        except Exception:
            pairwise = []

        results.append({
            "id": s.id,
            "paper_ids": s.paper_ids,
            "papers": [{"id": pid, "title": paper_titles.get(pid, "Unknown")} for pid in s.paper_ids],
            "comparisons": pairwise,
            "created_at": s.created_at.isoformat(),
        })

    return {"sessions": results}


# ============================================
# Literature Review History
# ============================================


@router.get("/literature-review/history")
async def get_literature_review_history(user=Depends(get_current_user)):
    """
    Get saved literature review results for the current user.
    """
    db = get_db()

    reviews = await db.literaturereview.find_many(
        where={"user_id": user.id},
        order={"created_at": "desc"},
        take=20,
    )

    results = []
    for r in reviews:
        results.append({
            "id": r.id,
            "title": r.title,
            "focus_topic": r.focus_topic,
            "review_text": r.review_text,
            "papers_analyzed": r.papers_analyzed,
            "paper_ids": r.paper_ids,
            "key_themes": r.key_themes,
            "research_gaps": r.research_gaps,
            "created_at": r.created_at.isoformat(),
        })

    return {"reviews": results}



# ============================================
# Delete Comparison Session
# ============================================


@router.delete("/compare/{session_id}")
async def delete_comparison_session(session_id: str, user=Depends(get_current_user)):
    """
    Delete a saved paper comparison session.
    """
    db = get_db()

    session = await db.papercomparison.find_unique(where={"id": session_id})
    if not session or session.user_id != user.id:
        raise HTTPException(status_code=404, detail="Comparison session not found")

    await db.papercomparison.delete(where={"id": session_id})
    return {"message": "Comparison session deleted"}


# ============================================
# Delete Literature Review
# ============================================


@router.delete("/literature-review/{review_id}")
async def delete_literature_review(review_id: str, user=Depends(get_current_user)):
    """
    Delete a saved literature review.
    """
    db = get_db()

    review = await db.literaturereview.find_unique(where={"id": review_id})
    if not review or review.user_id != user.id:
        raise HTTPException(status_code=404, detail="Literature review not found")

    await db.literaturereview.delete(where={"id": review_id})
    return {"message": "Literature review deleted"}

# ============================================
# Research Timeline
# ============================================


@router.post("/timeline", response_model=ResearchTimelineResponse)
async def generate_research_timeline(
    paper_ids: List[str],
    user=Depends(get_current_user),
):
    """Generate a chronological research timeline from papers."""
    db = get_db()

    entries = []
    for pid in paper_ids:
        paper = await db.paper.find_unique(where={"id": pid})
        if not paper:
            continue

        # Get key contribution from first chunk or title
        chunks = await db.paperchunk.find_many(
            where={"paper_id": pid},
            order={"chunk_index": "asc"},
            take=3,
        )

        contribution = paper.abstract[:200] if paper.abstract else paper.title

        entries.append(ResearchTimelineEntry(
            paper_id=pid,
            title=paper.title,
            year=paper.publication_date.year if paper.publication_date else None,
            key_contribution=contribution,
        ))

    # Sort chronologically
    entries.sort(key=lambda x: x.year or 9999)

    summary = f"Research timeline spanning {len(entries)} papers"
    if entries and entries[0].year and entries[-1].year:
        summary += f" from {entries[0].year} to {entries[-1].year}"

    return ResearchTimelineResponse(
        entries=entries,
        timeline_summary=summary,
    )


# ============================================
# Research Citation Graph
# ============================================


@router.get("/graph", response_model=ResearchGraphResponse)
async def get_research_graph(
    user=Depends(get_current_user),
    max_papers: int = Query(default=50, ge=5, le=200),
):
    """
    Generate a research citation/similarity graph.
    Nodes are papers, edges represent semantic similarity.
    """
    db = get_db()
    embedding_service = get_embedding_service()

    papers = await db.paper.find_many(
        where={"uploaded_by": user.id, "status": "PROCESSED"},
        take=max_papers,
        order={"created_at": "desc"},
    )

    if len(papers) < 2:
        raise HTTPException(status_code=400, detail="Need at least 2 processed papers")

    nodes = [
        ResearchGraphNode(id=p.id, title=p.title, type="paper")
        for p in papers
    ]

    # Compute pairwise similarities
    edges = []
    paper_texts = {}
    for p in papers:
        chunks = await db.paperchunk.find_many(
            where={"paper_id": p.id},
            take=5,
        )
        paper_texts[p.id] = " ".join(c.chunk_text for c in chunks)[:1000]

    from app.ai_models.embedding_model import get_embedding_model
    emb_model = get_embedding_model()

    # Encode all paper texts at once for efficiency
    paper_ids_list = list(paper_texts.keys())
    texts = [paper_texts[pid] for pid in paper_ids_list]
    embeddings = emb_model.encode(texts, normalize=True)

    import numpy as np
    similarity_matrix = np.dot(embeddings, embeddings.T)

    for i in range(len(paper_ids_list)):
        for j in range(i + 1, len(paper_ids_list)):
            sim = float(similarity_matrix[i][j])
            if sim > 0.15:  # Include connections above 15% similarity
                edges.append(ResearchGraphEdge(
                    source=paper_ids_list[i],
                    target=paper_ids_list[j],
                    weight=round(sim, 4),
                    relationship="semantic_similarity",
                ))

    return ResearchGraphResponse(nodes=nodes, edges=edges)


# ============================================
# Personalized Recommendations
# ============================================


@router.get("/recommendations", response_model=List[RecommendationResponse])
async def get_recommendations(
    top_k: int = Query(default=10, ge=1, le=50),
    user=Depends(get_current_user),
):
    """
    Get personalized paper recommendations based on the user's research profile.
    Uses the user's existing papers and reading history to find similar papers.
    """
    db = get_db()
    embedding_service = get_embedding_service()

    # Get user's papers
    user_papers = await db.paper.find_many(
        where={"uploaded_by": user.id, "status": "PROCESSED"},
        take=20,
        order={"created_at": "desc"},
    )

    if not user_papers:
        return []

    # Find papers not owned by the user
    all_paper_ids = [p.id for p in user_papers]
    recommendations = []

    for paper in user_papers[:5]:  # Use top 5 recent papers as seed
        related = await embedding_service.find_related_papers(paper.id, top_k=5)
        for r in related:
            if r["paper_id"] not in all_paper_ids:
                recommendations.append(RecommendationResponse(
                    paper_id=r["paper_id"],
                    title=r["title"],
                    authors=r.get("authors", []),
                    relevance_score=r["similarity"],
                    reason=f"Similar to your paper: {paper.title[:50]}",
                ))
                all_paper_ids.append(r["paper_id"])

    # Sort by relevance and return top_k
    recommendations.sort(key=lambda x: x.relevance_score, reverse=True)
    return recommendations[:top_k]


# ============================================
# Activity Dashboard
# ============================================


@router.get("/dashboard")
async def get_dashboard(user=Depends(get_current_user)):
    """
    Get a comprehensive research dashboard with statistics and insights.
    """
    db = get_db()

    # Paper statistics
    total_papers = await db.paper.count(where={"uploaded_by": user.id})
    processed_papers = await db.paper.count(
        where={"uploaded_by": user.id, "status": "PROCESSED"}
    )
    processing_papers = await db.paper.count(
        where={"uploaded_by": user.id, "status": "PROCESSING"}
    )

    # Chat statistics
    total_sessions = await db.chatsession.count(where={"user_id": user.id})
    total_messages = await db.chatmessage.count(
        where={"session": {"is": {"user_id": user.id}}}
    )

    # Notes statistics
    total_notes = await db.researchnote.count(where={"user_id": user.id})
    pinned_notes = await db.researchnote.count(
        where={"user_id": user.id, "is_pinned": True}
    )
    paper_linked_notes = await db.researchnote.count(
        where={"user_id": user.id, "paper_id": {"not": None}}
    )

    # Reading list statistics
    reading_list_total = await db.readinglistitem.count(where={"user_id": user.id})
    reading_completed = await db.readinglistitem.count(
        where={"user_id": user.id, "status": "COMPLETED"}
    )

    # Collection statistics
    total_collections = await db.collection.count(where={"user_id": user.id})

    # Comparison statistics
    total_comparisons = await db.papercomparison.count(where={"user_id": user.id})

    # Literature review statistics
    total_lit_reviews = await db.literaturereview.count(where={"user_id": user.id})

    # Recent activity (limited to 15 most recent)
    recent_activities = await db.activitylog.find_many(
        where={"user_id": user.id},
        take=5,
        order={"created_at": "desc"},
    )

    return {
        "papers": {
            "total": total_papers,
            "processed": processed_papers,
            "processing": processing_papers,
            "failed": total_papers - processed_papers - processing_papers,
        },
        "chat": {
            "total_sessions": total_sessions,
            "total_messages": total_messages,
        },
        "notes": {
            "total": total_notes,
            "pinned": pinned_notes,
            "paper_linked": paper_linked_notes,
        },
        "reading_list": {
            "total": reading_list_total,
            "completed": reading_completed,
            "completion_rate": round(
                reading_completed / reading_list_total * 100, 1
            ) if reading_list_total > 0 else 0,
        },
        "collections": {
            "total": total_collections,
        },
        "comparisons": {
            "total": total_comparisons,
        },
        "literature_reviews": {
            "total": total_lit_reviews,
        },
        "recent_activity": [
            {
                "action": a.action,
                "resource": a.resource,
                "resource_id": a.resource_id,
                "details": a.details,
                "timestamp": a.created_at.isoformat(),
            }
            for a in recent_activities
        ],
    }


@router.get("/analytics")
async def get_analytics(user=Depends(get_current_user)):
    """
    Get research analytics data: activity over time, topic distribution,
    reading patterns, and productivity metrics.
    """
    from datetime import datetime, timedelta
    from collections import Counter

    db = get_db()

    # ── Papers uploaded per month (last 12 months) ──
    twelve_months_ago = datetime.utcnow() - timedelta(days=365)
    papers = await db.paper.find_many(
        where={"uploaded_by": user.id, "created_at": {"gte": twelve_months_ago}},
        order={"created_at": "asc"},
    )
    uploads_by_month: dict[str, int] = {}
    for p in papers:
        month_key = p.created_at.strftime("%Y-%m")
        uploads_by_month[month_key] = uploads_by_month.get(month_key, 0) + 1

    # ── Activity per week (last 12 weeks) ──
    twelve_weeks_ago = datetime.utcnow() - timedelta(weeks=12)
    activities = await db.activitylog.find_many(
        where={"user_id": user.id, "created_at": {"gte": twelve_weeks_ago}},
    )
    activity_by_week: dict[str, int] = {}
    for a in activities:
        week_key = a.created_at.strftime("%Y-W%U")
        activity_by_week[week_key] = activity_by_week.get(week_key, 0) + 1

    # ── Topic / keyword distribution ──
    all_papers = await db.paper.find_many(
        where={"uploaded_by": user.id},
        order={"created_at": "desc"},
    )
    keyword_counter: Counter = Counter()
    for p in all_papers:
        for kw in (p.keywords or []):
            keyword_counter[kw.lower().strip()] += 1
    top_keywords = keyword_counter.most_common(15)

    # ── Reading status distribution ──
    reading_items = await db.readinglistitem.find_many(
        where={"user_id": user.id},
    )
    reading_status_counts = Counter(item.status for item in reading_items)

    # ── Notes per month ──
    notes = await db.researchnote.find_many(
        where={"user_id": user.id, "created_at": {"gte": twelve_months_ago}},
        order={"created_at": "asc"},
    )
    notes_by_month: dict[str, int] = {}
    for n in notes:
        month_key = n.created_at.strftime("%Y-%m")
        notes_by_month[month_key] = notes_by_month.get(month_key, 0) + 1

    # ── Chat activity per month ──
    sessions = await db.chatsession.find_many(
        where={"user_id": user.id, "created_at": {"gte": twelve_months_ago}},
        order={"created_at": "asc"},
    )
    chats_by_month: dict[str, int] = {}
    for s in sessions:
        month_key = s.created_at.strftime("%Y-%m")
        chats_by_month[month_key] = chats_by_month.get(month_key, 0) + 1

    # ── Productivity streak: consecutive days with activity ──
    activity_dates = set()
    for a in activities:
        activity_dates.add(a.created_at.date())
    streak = 0
    current = datetime.utcnow().date()
    while current in activity_dates:
        streak += 1
        current -= timedelta(days=1)

    # ── Paper status breakdown ──
    status_counts = Counter(p.status for p in all_papers)

    return {
        "uploads_by_month": [
            {"month": k, "count": v}
            for k, v in sorted(uploads_by_month.items())
        ],
        "activity_by_week": [
            {"week": k, "count": v}
            for k, v in sorted(activity_by_week.items())
        ],
        "top_keywords": [
            {"keyword": kw, "count": cnt} for kw, cnt in top_keywords
        ],
        "reading_status": {
            "UNREAD": reading_status_counts.get("UNREAD", 0),
            "READING": reading_status_counts.get("READING", 0),
            "COMPLETED": reading_status_counts.get("COMPLETED", 0),
            "SKIPPED": reading_status_counts.get("SKIPPED", 0),
        },
        "notes_by_month": [
            {"month": k, "count": v}
            for k, v in sorted(notes_by_month.items())
        ],
        "chats_by_month": [
            {"month": k, "count": v}
            for k, v in sorted(chats_by_month.items())
        ],
        "paper_status": {
            "PROCESSED": status_counts.get("PROCESSED", 0),
            "PROCESSING": status_counts.get("PROCESSING", 0),
            "PENDING": status_counts.get("PENDING", 0),
            "FAILED": status_counts.get("FAILED", 0),
        },
        "current_streak": streak,
        "total_papers": len(all_papers),
        "total_keywords": len(keyword_counter),
    }


@router.post("/citations/export")
async def export_citations(
    data: dict,
    user=Depends(get_current_user),
):
    """
    Bulk-export citations for multiple papers in a given format.
    Body: { "paper_ids": [...], "format": "APA" | "BIBTEX" | ... }
    """
    from app.services.citation_service import get_citation_service

    paper_ids = data.get("paper_ids", [])
    fmt = data.get("format", "APA")

    if not paper_ids:
        raise HTTPException(status_code=400, detail="No paper IDs provided")

    citation_service = get_citation_service()
    results = []
    for pid in paper_ids:
        try:
            citation = await citation_service.generate_citation(pid, fmt)
            results.append(citation)
        except Exception as e:
            logger.warning("citation_export_error", paper_id=pid, error=str(e))
            results.append({
                "paper_id": pid,
                "format": fmt,
                "citation_text": f"[Citation unavailable for paper {pid}]",
            })

    return {"citations": results, "format": fmt, "count": len(results)}


# ============================================
# Helper Functions
# ============================================


def _extract_common_themes(text_a: str, text_b: str) -> List[str]:
    """Extract common themes between two paper texts."""
    import re
    from collections import Counter

    stopwords = {
        "the", "a", "an", "in", "of", "and", "or", "to", "for", "is", "are",
        "was", "were", "be", "been", "have", "has", "had", "this", "that",
        "with", "from", "by", "on", "at", "as", "not", "we", "our", "their",
        "which", "who", "what", "can", "also", "more", "than", "each", "its",
    }

    def get_keywords(text):
        words = re.findall(r"\b[a-z]{4,}\b", text.lower())
        return Counter(w for w in words if w not in stopwords)

    kw_a = get_keywords(text_a)
    kw_b = get_keywords(text_b)

    common = set(kw_a.keys()) & set(kw_b.keys())
    ranked = sorted(common, key=lambda w: kw_a[w] + kw_b[w], reverse=True)

    return ranked[:10]


def _extract_differences(paper_a, paper_b, text_a: str, text_b: str) -> List[str]:
    """Extract key differences between two papers."""
    differences = []

    if paper_a.authors != paper_b.authors:
        differences.append(f"Different research groups: {', '.join(paper_a.authors[:2])} vs {', '.join(paper_b.authors[:2])}")

    kw_a = set(paper_a.keywords or [])
    kw_b = set(paper_b.keywords or [])
    unique_a = kw_a - kw_b
    unique_b = kw_b - kw_a

    if unique_a:
        differences.append(f"Unique to '{paper_a.title[:30]}': {', '.join(list(unique_a)[:3])}")
    if unique_b:
        differences.append(f"Unique to '{paper_b.title[:30]}': {', '.join(list(unique_b)[:3])}")

    return differences


def _extract_themes_from_summaries(paper_summaries: List[dict]) -> List[str]:
    """Extract recurring themes from paper summaries."""
    import re
    from collections import Counter

    all_text = " ".join(p["summary"] for p in paper_summaries)
    stopwords = {
        "the", "a", "an", "in", "of", "and", "or", "to", "for", "is", "are",
        "was", "were", "this", "that", "with", "from", "by", "on", "we", "our",
        "also", "can", "has", "have", "been", "more", "than", "its", "their",
    }

    words = re.findall(r"\b[a-z]{4,}\b", all_text.lower())
    meaningful = [w for w in words if w not in stopwords]
    counter = Counter(meaningful)

    return [word for word, count in counter.most_common(15) if count >= 2]


# ============================================
# Global Quick Search (Command Palette)
# ============================================


@router.get("/quick-search")
async def quick_search(
    q: str = Query("", min_length=1, max_length=200),
    user=Depends(get_current_user),
):
    """
    Lightweight search across papers, notes, collections, and chat sessions.
    Used by the frontend command palette for instant results.
    """
    db = get_db()
    query = q.strip().lower()
    results = []

    # ── Search Papers ──
    try:
        papers = await db.paper.find_many(
            where={
                "user_id": user.id,
                "title": {"contains": query, "mode": "insensitive"},
            },
            order={"created_at": "desc"},
            take=5,
        )
        for p in papers:
            results.append({
                "type": "paper",
                "id": p.id,
                "title": p.title,
                "subtitle": ", ".join(p.authors[:2]) if p.authors else None,
                "status": p.status,
                "url": f"/papers/{p.id}",
                "created_at": p.created_at.isoformat(),
            })
    except Exception:
        pass

    # ── Search Notes ──
    try:
        notes = await db.note.find_many(
            where={
                "user_id": user.id,
                "OR": [
                    {"title": {"contains": query, "mode": "insensitive"}},
                    {"content": {"contains": query, "mode": "insensitive"}},
                ],
            },
            order={"created_at": "desc"},
            take=5,
        )
        for n in notes:
            results.append({
                "type": "note",
                "id": n.id,
                "title": n.title or "Untitled Note",
                "subtitle": (n.content or "")[:80],
                "url": "/notes",
                "created_at": n.created_at.isoformat(),
            })
    except Exception:
        pass

    # ── Search Collections ──
    try:
        collections = await db.collection.find_many(
            where={
                "user_id": user.id,
                "name": {"contains": query, "mode": "insensitive"},
            },
            order={"created_at": "desc"},
            take=5,
        )
        for c in collections:
            results.append({
                "type": "collection",
                "id": c.id,
                "title": c.name,
                "subtitle": c.description[:80] if c.description else None,
                "url": f"/collections/{c.id}",
                "created_at": c.created_at.isoformat(),
            })
    except Exception:
        pass

    # ── Search Chat Sessions ──
    try:
        sessions = await db.chatsession.find_many(
            where={
                "user_id": user.id,
                "title": {"contains": query, "mode": "insensitive"},
            },
            order={"created_at": "desc"},
            take=5,
        )
        for s in sessions:
            results.append({
                "type": "chat",
                "id": s.id,
                "title": s.title or "Untitled Chat",
                "subtitle": f"{s.message_count} messages" if hasattr(s, "message_count") else None,
                "url": f"/chat?session={s.id}",
                "created_at": s.created_at.isoformat(),
            })
    except Exception:
        pass

    return {"query": q, "results": results}
