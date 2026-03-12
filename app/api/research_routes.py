# ============================================
# API Routes - Research (Summarization, Insights, Clustering)
# ============================================

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from prisma import Json

from app.database.prisma_client import get_db
from app.middleware.auth import get_current_user
from app.schemas.paper_schema import (
    ClusterRunRequest,
    ClusterRunResponse,
    PaperInsightResponse,
    PaperSummaryResponse,
    TopicClusterResponse,
)
from app.services.clustering_service import get_clustering_service
from app.services.summarization_service import get_summarization_service

logger = structlog.get_logger()
router = APIRouter()


@router.post("/summarize/{paper_id}", response_model=PaperSummaryResponse)
async def summarize_paper(
    paper_id: str,
    summary_type: str = Query(default="STRUCTURED", regex="^(STRUCTURED|BRIEF|DETAILED|ABSTRACT)$"),
    force: bool = False,
    user=Depends(get_current_user),
):
    """
    Generate a structured summary of a research paper.
    
    Summary types:
    - STRUCTURED: Background, methodology, results, limitations, conclusions
    - BRIEF: Short one-paragraph summary
    - DETAILED: Multi-paragraph comprehensive summary
    - ABSTRACT: Regenerated abstract
    """
    db = get_db()

    paper = await db.paper.find_unique(where={"id": paper_id})
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    if paper.uploaded_by != user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    if paper.status != "PROCESSED":
        raise HTTPException(status_code=400, detail="Paper has not been processed yet")

    summarization_service = get_summarization_service()

    try:
        summary = await summarization_service.summarize_paper(
            paper_id=paper_id,
            summary_type=summary_type,
            force_regenerate=force,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("summarization_failed", paper_id=paper_id, error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Summarization failed: {str(e)[:200]}",
        )

    # Log activity
    await db.activitylog.create(
        data={
            "user_id": user.id,
            "action": "PAPER_SUMMARIZED",
            "resource": "paper",
            "resource_id": paper_id,
            "details": Json({"summary_type": summary_type}),
        }
    )

    return PaperSummaryResponse(
        id=summary["id"],
        summary_type=summary["summary_type"],
        background=summary.get("background"),
        methodology=summary.get("methodology"),
        results=summary.get("results"),
        limitations=summary.get("limitations"),
        conclusions=summary.get("conclusions"),
        full_summary=summary.get("full_summary"),
        created_at=summary["created_at"],
    )


@router.post("/insights/{paper_id}", response_model=PaperInsightResponse)
async def extract_insights(paper_id: str, user=Depends(get_current_user)):
    """
    Extract research insights from a paper.
    
    Generates:
    - Key contributions
    - Research gaps
    - Future work ideas
    - Methodology notes
    - Strengths and weaknesses
    """
    db = get_db()

    paper = await db.paper.find_unique(where={"id": paper_id})
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    if paper.uploaded_by != user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    # Check for cached insights
    existing = await db.paperinsight.find_first(where={"paper_id": paper_id})
    if existing:
        return PaperInsightResponse(
            id=existing.id,
            paper_id=existing.paper_id,
            key_contributions=existing.key_contributions,
            research_gaps=existing.research_gaps,
            future_work=existing.future_work,
            methodology_notes=existing.methodology_notes,
            strengths=existing.strengths,
            weaknesses=existing.weaknesses,
            created_at=existing.created_at,
        )

    # Get paper chunks for analysis
    chunks = await db.paperchunk.find_many(
        where={"paper_id": paper_id},
        order={"chunk_index": "asc"},
    )

    if not chunks:
        raise HTTPException(status_code=400, detail="Paper has not been processed")

    # Use QA model to extract targeted insights from relevant sections
    from app.ai_models.qa_model import get_qa_model
    from app.ai_models.summarizer_model import get_summarizer_model

    qa = get_qa_model()
    summarizer = get_summarizer_model()
    full_text = " ".join(c.chunk_text for c in chunks)

    # Generate insights using QA-based extraction
    insights_data = _extract_insights_from_text(qa, summarizer, full_text)

    # Store insights
    insight = await db.paperinsight.create(
        data={
            "paper_id": paper_id,
            "key_contributions": insights_data["key_contributions"],
            "research_gaps": insights_data["research_gaps"],
            "future_work": insights_data["future_work"],
            "methodology_notes": insights_data["methodology_notes"],
            "strengths": insights_data["strengths"],
            "weaknesses": insights_data["weaknesses"],
        }
    )

    # Log activity
    await db.activitylog.create(
        data={
            "user_id": user.id,
            "action": "INSIGHTS_EXTRACTED",
            "resource": "paper",
            "resource_id": paper_id,
        }
    )

    return PaperInsightResponse(
        id=insight.id,
        paper_id=insight.paper_id,
        key_contributions=insight.key_contributions,
        research_gaps=insight.research_gaps,
        future_work=insight.future_work,
        methodology_notes=insight.methodology_notes,
        strengths=insight.strengths,
        weaknesses=insight.weaknesses,
        created_at=insight.created_at,
    )


def _extract_insights_from_text(qa, summarizer, text: str) -> dict:
    """
    Extract structured insights from paper text using the QA model
    for targeted question-answering and the summarizer for condensation.
    """
    import re

    words = text.split()
    text_truncated = " ".join(words[:2000]) if len(words) > 2000 else text

    # Define targeted questions for each insight category
    qa_questions = {
        "key_contributions": [
            "What are the main contributions of this work?",
            "What novel approach or method does this paper propose?",
            "What are the key findings or results?",
        ],
        "research_gaps": [
            "What problems or limitations does this paper address?",
            "What challenges or gaps exist in current research?",
            "What issues remain unsolved?",
        ],
        "future_work": [
            "What future work or directions are suggested?",
            "How could this work be extended or improved?",
            "What are the next steps for this research?",
        ],
        "methodology_notes": [
            "What methods or techniques are used in this work?",
            "What tools, frameworks, or technologies are employed?",
            "What is the approach or methodology?",
        ],
        "strengths": [
            "What are the strengths or advantages of this approach?",
            "What results show improvement or success?",
            "What makes this work significant?",
        ],
        "weaknesses": [
            "What are the limitations or weaknesses of this work?",
            "What constraints or drawbacks does this approach have?",
            "What could be improved?",
        ],
    }

    insights: dict = {}

    for category, questions in qa_questions.items():
        answers = []
        seen = set()

        for question in questions:
            try:
                result = qa.answer(question, text_truncated, top_k=1)
                for ans in result:
                    answer_text = ans.get("answer", "").strip()
                    score = ans.get("score", 0)

                    # Only keep answers with reasonable confidence
                    if (
                        answer_text
                        and score > 0.01
                        and len(answer_text) > 5
                        and answer_text.lower() not in seen
                    ):
                        # Expand short answers by finding the full sentence
                        if len(answer_text.split()) < 8:
                            expanded = _find_containing_sentence(text_truncated, answer_text)
                            if expanded and len(expanded) > len(answer_text):
                                answer_text = expanded
                        seen.add(answer_text.lower())
                        answers.append(answer_text)
            except Exception as e:
                logger.warning(
                    "insight_qa_failed", category=category, error=str(e)
                )

        # If QA produced nothing useful, try sentence-level extraction
        if not answers:
            answers = _extract_sentences_for_category(text_truncated, category)

        insights[category] = answers[:5]

    return insights


def _find_containing_sentence(text: str, fragment: str) -> str:
    """Find the full sentence containing the given text fragment."""
    import re

    # Split into sentences
    sentences = re.split(r'(?<=[.!?])\s+', text)
    fragment_lower = fragment.lower()

    for sentence in sentences:
        if fragment_lower in sentence.lower():
            cleaned = sentence.strip()
            if 15 < len(cleaned) < 300:
                return cleaned
    return fragment


def _extract_sentences_for_category(text: str, category: str) -> list:
    """
    Fallback: extract relevant sentences based on keyword matching.
    Uses different keywords per category to avoid duplicate content.
    """
    import re

    keywords = {
        "key_contributions": [
            "propose", "present", "introduce", "develop", "novel", "contribute",
            "demonstrate", "achieve", "design", "implement", "create", "build",
        ],
        "research_gaps": [
            "however", "challenge", "gap", "problem", "limitation", "lack",
            "insufficient", "issue", "difficult", "remain", "unsolved",
        ],
        "future_work": [
            "future", "extend", "improve", "plan", "could", "should",
            "further", "next", "explore", "potential", "enhance",
        ],
        "methodology_notes": [
            "method", "technique", "algorithm", "framework", "approach",
            "model", "architecture", "pipeline", "process", "tool",
            "dataset", "training", "evaluation",
        ],
        "strengths": [
            "significant", "outperform", "improve", "effective", "robust",
            "accurate", "efficient", "superior", "advantage", "state-of-the-art",
            "achieve", "success", "better",
        ],
        "weaknesses": [
            "limitation", "drawback", "weakness", "fail", "unable",
            "constraint", "restrict", "shortcoming", "does not", "cannot",
            "difficulty", "bottleneck",
        ],
    }

    category_kws = keywords.get(category, [])
    sentences = re.split(r'(?<=[.!?])\s+', text)
    results = []
    seen = set()

    # Score sentences by keyword relevance
    scored = []
    for s in sentences:
        s = s.strip()
        if len(s) < 20 or len(s) > 400:
            continue
        s_lower = s.lower()
        score = sum(1 for kw in category_kws if kw in s_lower)
        if score > 0:
            scored.append((score, s))

    # Sort by relevance score
    scored.sort(key=lambda x: x[0], reverse=True)

    for _, sentence in scored[:5]:
        normalized = sentence.lower().strip()
        if normalized not in seen:
            seen.add(normalized)
            results.append(sentence)

    # If still nothing, pick sentences from different parts of the text
    if not results:
        total = len(sentences)
        offsets = {
            "key_contributions": (0, total // 3),
            "research_gaps": (total // 4, total // 2),
            "future_work": (2 * total // 3, total),
            "methodology_notes": (total // 6, total // 2),
            "strengths": (total // 3, 2 * total // 3),
            "weaknesses": (total // 2, 5 * total // 6),
        }
        start, end = offsets.get(category, (0, total))
        for s in sentences[start:end]:
            s = s.strip()
            if len(s) > 30 and s.lower() not in seen:
                seen.add(s.lower())
                results.append(s)
                if len(results) >= 3:
                    break

    return results[:5]


@router.post("/clusters/run", response_model=ClusterRunResponse)
async def run_clustering(request: ClusterRunRequest, user=Depends(get_current_user)):
    """
    Run topic clustering on all papers.
    Groups papers into semantic clusters using KMeans or HDBSCAN.
    """
    clustering_service = get_clustering_service()

    try:
        result = await clustering_service.run_clustering(
            algorithm=request.algorithm,
            n_clusters=request.n_clusters,
            min_cluster_size=request.min_cluster_size,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return ClusterRunResponse(
        clusters=[
            TopicClusterResponse(
                id=c["id"],
                name=c["name"],
                description=c.get("description"),
                keywords=c["keywords"],
                paper_count=c["paper_count"],
            )
            for c in result["clusters"]
        ],
        total_papers=result["total_papers"],
        algorithm=result["algorithm"],
    )


@router.get("/clusters", response_model=list[TopicClusterResponse])
async def get_clusters(user=Depends(get_current_user)):
    """Get all topic clusters."""
    clustering_service = get_clustering_service()
    clusters = await clustering_service.get_clusters()

    return [
        TopicClusterResponse(
            id=c["id"],
            name=c["name"],
            description=c.get("description"),
            keywords=c["keywords"],
            paper_count=c["paper_count"],
        )
        for c in clusters
    ]
