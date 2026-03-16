# ============================================
# API Routes - Research Gap Analyzer
# ============================================

from __future__ import annotations

import json
from typing import List, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from prisma import Json

from app.config import settings
from app.database.prisma_client import get_db
from app.middleware.auth import get_current_user

logger = structlog.get_logger()
router = APIRouter()


# ============================================
# Schemas
# ============================================


class GapItem(BaseModel):
    gap: str
    description: str
    severity: str  # high, medium, low


class ResearchIdea(BaseModel):
    idea: str
    description: str
    feasibility: str  # high, medium, low
    impact: str  # high, medium, low


class GapAnalysisResponse(BaseModel):
    id: str
    paper_id: str
    paper_title: str
    title: str
    gaps: List[GapItem]
    research_ideas: List[ResearchIdea]
    methodology_gaps: List[str]
    data_gaps: List[str]
    summary: str
    created_at: str


class GapAnalysisHistoryItem(BaseModel):
    id: str
    paper_id: str
    paper_title: str
    title: str
    summary: str
    gap_count: int
    idea_count: int
    created_at: str


# ============================================
# Analyze Paper for Research Gaps
# ============================================


@router.post("/analyze/{paper_id}", response_model=GapAnalysisResponse)
async def analyze_paper_gaps(paper_id: str, force: bool = False, user=Depends(get_current_user)):
    """
    Analyze a research paper to identify gaps and generate future research ideas.

    Uses LLM to deeply analyze the paper content and produce:
    - Research gaps with severity ratings
    - Actionable research ideas with feasibility and impact ratings
    - Methodology gaps
    - Data/evidence gaps
    - Overall summary
    """
    db = get_db()

    paper = await db.paper.find_unique(where={"id": paper_id})
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    if paper.uploaded_by != user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    if paper.status != "PROCESSED":
        raise HTTPException(status_code=400, detail="Paper has not been processed yet")

    # Check for existing analysis (unless force regenerate)
    if not force:
        existing = await db.gapanalysis.find_first(
            where={"paper_id": paper_id, "user_id": user.id},
            order={"created_at": "desc"},
        )
        if existing:
            return _format_analysis_response(existing, paper.title)

    # Get paper chunks
    chunks = await db.paperchunk.find_many(
        where={"paper_id": paper_id},
        order={"chunk_index": "asc"},
    )

    if not chunks:
        raise HTTPException(status_code=400, detail="Paper has no processed content")

    full_text = " ".join(c.chunk_text for c in chunks)
    words = full_text.split()
    text_for_analysis = " ".join(words[:3000]) if len(words) > 3000 else full_text

    # Build LLM prompt for gap analysis
    prompt = _build_gap_analysis_prompt(paper.title, paper.authors, paper.abstract, text_for_analysis)

    try:
        from huggingface_hub import InferenceClient

        client = InferenceClient(token=settings.HUGGINGFACE_API_TOKEN)
        response = client.chat_completion(
            model=settings.GENERATIVE_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are an expert research analyst specializing in identifying research gaps "
                        "and generating actionable future research directions. Always respond with valid JSON."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            max_tokens=2048,
            temperature=0.3,
        )
        raw_response = response.choices[0].message.content or ""
        analysis = _parse_llm_response(raw_response)
    except Exception as e:
        logger.error("gap_analysis_llm_failed", paper_id=paper_id, error=str(e))
        analysis = _generate_fallback_analysis(paper.title, text_for_analysis)

    # Save to database
    record = await db.gapanalysis.create(
        data={
            "user_id": user.id,
            "paper_id": paper_id,
            "title": f"Gap Analysis: {paper.title[:80]}",
            "gaps": Json(analysis["gaps"]),
            "research_ideas": Json(analysis["research_ideas"]),
            "methodology_gaps": analysis["methodology_gaps"],
            "data_gaps": analysis["data_gaps"],
            "summary": analysis["summary"],
        }
    )

    # Log activity
    await db.activitylog.create(
        data={
            "user_id": user.id,
            "action": "GAP_ANALYSIS_RUN",
            "resource": "paper",
            "resource_id": paper_id,
            "details": Json({"gap_count": len(analysis["gaps"]), "idea_count": len(analysis["research_ideas"])}),
        }
    )

    return _format_analysis_response(record, paper.title)


# ============================================
# History & Detail
# ============================================


@router.get("/history", response_model=List[GapAnalysisHistoryItem])
async def get_gap_analysis_history(user=Depends(get_current_user)):
    """List all gap analyses for the current user."""
    db = get_db()

    analyses = await db.gapanalysis.find_many(
        where={"user_id": user.id},
        order={"created_at": "desc"},
        include={"paper": True},
    )

    return [
        GapAnalysisHistoryItem(
            id=a.id,
            paper_id=a.paper_id,
            paper_title=a.paper.title if a.paper else "Unknown Paper",
            title=a.title,
            summary=a.summary[:200] + "..." if len(a.summary) > 200 else a.summary,
            gap_count=len(a.gaps) if isinstance(a.gaps, list) else 0,
            idea_count=len(a.research_ideas) if isinstance(a.research_ideas, list) else 0,
            created_at=a.created_at.isoformat(),
        )
        for a in analyses
    ]


@router.get("/{analysis_id}", response_model=GapAnalysisResponse)
async def get_gap_analysis(analysis_id: str, user=Depends(get_current_user)):
    """Get a specific gap analysis by ID."""
    db = get_db()

    analysis = await db.gapanalysis.find_unique(
        where={"id": analysis_id},
        include={"paper": True},
    )

    if not analysis:
        raise HTTPException(status_code=404, detail="Gap analysis not found")
    if analysis.user_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    paper_title = analysis.paper.title if analysis.paper else "Unknown Paper"
    return _format_analysis_response(analysis, paper_title)


@router.delete("/{analysis_id}")
async def delete_gap_analysis(analysis_id: str, user=Depends(get_current_user)):
    """Delete a gap analysis."""
    db = get_db()

    analysis = await db.gapanalysis.find_unique(where={"id": analysis_id})
    if not analysis:
        raise HTTPException(status_code=404, detail="Gap analysis not found")
    if analysis.user_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    await db.gapanalysis.delete(where={"id": analysis_id})
    return {"message": "Gap analysis deleted"}


# ============================================
# Helper Functions
# ============================================


def _build_gap_analysis_prompt(title: str, authors: list, abstract: str | None, text: str) -> str:
    author_str = ", ".join(authors[:5]) if authors else "Unknown"
    abstract_section = f"\nAbstract: {abstract}\n" if abstract else ""

    return f"""Analyze the following research paper and identify research gaps and future research directions.

Paper Title: "{title}"
Authors: {author_str}
{abstract_section}
Paper Content (excerpts):
{text}

Respond with a JSON object containing exactly these fields:
{{
  "gaps": [
    {{
      "gap": "Short title of the research gap",
      "description": "Detailed description of why this is a gap and what is missing",
      "severity": "high|medium|low"
    }}
  ],
  "research_ideas": [
    {{
      "idea": "Short title of the research idea",
      "description": "Detailed description of how this idea could be pursued",
      "feasibility": "high|medium|low",
      "impact": "high|medium|low"
    }}
  ],
  "methodology_gaps": ["List of methodology limitations or gaps"],
  "data_gaps": ["List of data/evidence gaps or missing datasets"],
  "summary": "A comprehensive 2-3 paragraph summary of the overall gap analysis, highlighting the most critical gaps and most promising research directions."
}}

Identify at least 3-5 gaps and 3-5 research ideas. Be specific and actionable. Reference actual content from the paper."""


def _parse_llm_response(raw: str) -> dict:
    """Parse the LLM JSON response, handling markdown code blocks."""
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        # Remove first line (```json) and last line (```)
        lines = [l for l in lines if not l.strip().startswith("```")]
        cleaned = "\n".join(lines)

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        # Try to find JSON object in the response
        start = cleaned.find("{")
        end = cleaned.rfind("}") + 1
        if start != -1 and end > start:
            try:
                parsed = json.loads(cleaned[start:end])
            except json.JSONDecodeError:
                return _empty_analysis("Failed to parse LLM response")
        else:
            return _empty_analysis("No JSON found in LLM response")

    # Validate and normalize the structure
    return {
        "gaps": parsed.get("gaps", []),
        "research_ideas": parsed.get("research_ideas", []),
        "methodology_gaps": parsed.get("methodology_gaps", []),
        "data_gaps": parsed.get("data_gaps", []),
        "summary": parsed.get("summary", "Analysis completed but no summary was generated."),
    }


def _empty_analysis(summary: str) -> dict:
    return {
        "gaps": [],
        "research_ideas": [],
        "methodology_gaps": [],
        "data_gaps": [],
        "summary": summary,
    }


def _generate_fallback_analysis(title: str, text: str) -> dict:
    """Generate a basic fallback analysis when the LLM call fails."""
    import re

    sentences = re.split(r"(?<=[.!?])\s+", text)
    gap_keywords = ["limitation", "challenge", "gap", "however", "future", "remain", "lack", "insufficient"]
    idea_keywords = ["could", "should", "future", "extend", "improve", "further", "explore", "potential"]

    gaps = []
    ideas = []

    for s in sentences:
        s = s.strip()
        if len(s) < 20 or len(s) > 400:
            continue
        s_lower = s.lower()
        if any(kw in s_lower for kw in gap_keywords) and len(gaps) < 3:
            gaps.append({"gap": "Identified gap", "description": s, "severity": "medium"})
        elif any(kw in s_lower for kw in idea_keywords) and len(ideas) < 3:
            ideas.append({"idea": "Potential direction", "description": s, "feasibility": "medium", "impact": "medium"})

    return {
        "gaps": gaps or [{"gap": "General research gaps", "description": f"The paper '{title}' may have unexplored areas that require further investigation.", "severity": "medium"}],
        "research_ideas": ideas or [{"idea": "Further investigation", "description": f"Extend the work in '{title}' with additional experiments or broader datasets.", "feasibility": "medium", "impact": "medium"}],
        "methodology_gaps": ["LLM analysis unavailable - manual review recommended"],
        "data_gaps": ["LLM analysis unavailable - manual review recommended"],
        "summary": f"Automated gap analysis for '{title}' could not be fully completed via LLM. A basic keyword-based extraction was performed. Please review the identified gaps manually for accuracy.",
    }


def _format_analysis_response(record, paper_title: str) -> GapAnalysisResponse:
    """Format a database record into the API response model."""
    gaps_data = record.gaps if isinstance(record.gaps, list) else []
    ideas_data = record.research_ideas if isinstance(record.research_ideas, list) else []

    return GapAnalysisResponse(
        id=record.id,
        paper_id=record.paper_id,
        paper_title=paper_title,
        title=record.title,
        gaps=[
            GapItem(
                gap=g.get("gap", "Unknown"),
                description=g.get("description", ""),
                severity=g.get("severity", "medium"),
            )
            for g in gaps_data
            if isinstance(g, dict)
        ],
        research_ideas=[
            ResearchIdea(
                idea=r.get("idea", "Unknown"),
                description=r.get("description", ""),
                feasibility=r.get("feasibility", "medium"),
                impact=r.get("impact", "medium"),
            )
            for r in ideas_data
            if isinstance(r, dict)
        ],
        methodology_gaps=record.methodology_gaps or [],
        data_gaps=record.data_gaps or [],
        summary=record.summary,
        created_at=record.created_at.isoformat(),
    )
