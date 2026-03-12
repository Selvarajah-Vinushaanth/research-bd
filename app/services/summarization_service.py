# ============================================
# Service - Summarization
# ============================================

from __future__ import annotations

import asyncio
import time
from typing import Dict, List, Optional

import structlog

from app.ai_models.summarizer_model import get_summarizer_model
from app.database.prisma_client import get_db
from app.utils.chunking import get_chunker

logger = structlog.get_logger()


class SummarizationService:
    """
    Research paper summarization service.
    Generates structured summaries with background, methodology, results, and limitations.
    Supports caching for repeated requests.
    """

    def __init__(self):
        self.model = get_summarizer_model()
        self.db = get_db()
        self.chunker = get_chunker()

    async def summarize_paper(
        self,
        paper_id: str,
        summary_type: str = "STRUCTURED",
        force_regenerate: bool = False,
    ) -> Dict:
        """
        Generate a structured summary of a research paper.

        Args:
            paper_id: The paper ID.
            summary_type: Type of summary (STRUCTURED, BRIEF, DETAILED, ABSTRACT).
            force_regenerate: Force regeneration even if cached.

        Returns:
            Dict with structured summary fields.
        """
        start_time = time.time()

        # Check for cached summary
        if not force_regenerate:
            existing = await self.db.papersummary.find_first(
                where={"paper_id": paper_id, "summary_type": summary_type}
            )
            if existing:
                logger.info("summary_cache_hit", paper_id=paper_id)
                return self._format_summary(existing)

        # Get paper chunks
        chunks = await self.db.paperchunk.find_many(
            where={"paper_id": paper_id},
            order={"chunk_index": "asc"},
        )

        if not chunks:
            raise ValueError(f"No text chunks found for paper {paper_id}")

        # Organize chunks by section
        section_texts = self._organize_by_section(chunks)
        full_text = " ".join(c.chunk_text for c in chunks)

        if summary_type == "STRUCTURED":
            summary_data = await self._generate_structured_summary(section_texts, full_text)
        elif summary_type == "BRIEF":
            summary_data = await self._generate_brief_summary(full_text)
        elif summary_type == "DETAILED":
            summary_data = await self._generate_detailed_summary(section_texts, full_text)
        else:
            summary_data = await self._generate_brief_summary(full_text)

        # Store the summary
        summary_record = await self.db.papersummary.create(
            data={
                "paper_id": paper_id,
                "summary_type": summary_type,
                "background": summary_data.get("background"),
                "methodology": summary_data.get("methodology"),
                "results": summary_data.get("results"),
                "limitations": summary_data.get("limitations"),
                "conclusions": summary_data.get("conclusions"),
                "full_summary": summary_data.get("full_summary"),
            }
        )

        elapsed = round(time.time() - start_time, 3)
        logger.info("summary_generated", paper_id=paper_id, type=summary_type, time=elapsed)

        return self._format_summary(summary_record)

    async def _generate_structured_summary(
        self,
        section_texts: Dict[str, str],
        full_text: str,
    ) -> Dict[str, str]:
        """Generate a structured summary with distinct sections."""
        summary = {}

        # Summarize each major section
        section_mapping = {
            "background": ["abstract", "introduction", "background", "related work"],
            "methodology": ["method", "methodology", "methods", "approach", "framework"],
            "results": ["results", "experiments", "evaluation", "findings"],
            "limitations": ["limitations", "discussion", "threats"],
            "conclusions": ["conclusion", "conclusions", "summary", "future work"],
        }

        for summary_key, section_names in section_mapping.items():
            combined_text = ""
            for section_name in section_names:
                if section_name in section_texts:
                    combined_text += " " + section_texts[section_name]

            if combined_text.strip() and len(combined_text.split()) > 30:
                try:
                    summary[summary_key] = await asyncio.to_thread(
                        self.model.summarize,
                        combined_text.strip(),
                        200,
                        50,
                    )
                except Exception as e:
                    logger.warning(f"section_summary_failed_{summary_key}", error=str(e))
                    summary[summary_key] = combined_text[:500].strip()

        # Generate overall summary
        summary["full_summary"] = await asyncio.to_thread(
            self.model.summarize_long_document, full_text, 350, 500
        )

        return summary

    async def _generate_brief_summary(self, full_text: str) -> Dict[str, str]:
        """Generate a brief one-paragraph summary."""
        summary_text = await asyncio.to_thread(
            self.model.summarize, full_text, 200, 80
        )
        return {"full_summary": summary_text}

    async def _generate_detailed_summary(
        self, section_texts: Dict[str, str], full_text: str
    ) -> Dict[str, str]:
        """Generate a detailed multi-paragraph summary."""
        summary = await self._generate_structured_summary(section_texts, full_text)
        # For detailed, generate a longer full_summary (reuse chunk
        # summaries already captured in structured step via the model).
        summary["full_summary"] = await asyncio.to_thread(
            self.model.summarize_long_document, full_text, 350, 800
        )
        return summary

    def _organize_by_section(self, chunks) -> Dict[str, str]:
        """Organize chunks by their section labels."""
        sections: Dict[str, List[str]] = {}
        for chunk in chunks:
            section = (chunk.section or "unknown").lower().strip()
            if section not in sections:
                sections[section] = []
            sections[section].append(chunk.chunk_text)

        return {k: " ".join(v) for k, v in sections.items()}

    def _format_summary(self, summary_record) -> Dict:
        """Format a summary record for API response."""
        return {
            "id": summary_record.id,
            "paper_id": summary_record.paper_id,
            "summary_type": summary_record.summary_type,
            "background": summary_record.background,
            "methodology": summary_record.methodology,
            "results": summary_record.results,
            "limitations": summary_record.limitations,
            "conclusions": summary_record.conclusions,
            "full_summary": summary_record.full_summary,
            "created_at": summary_record.created_at.isoformat(),
        }


def get_summarization_service() -> SummarizationService:
    return SummarizationService()
