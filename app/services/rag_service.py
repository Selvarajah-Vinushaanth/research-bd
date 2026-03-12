# ============================================
# Service - RAG (Retrieval Augmented Generation)
# ============================================

from __future__ import annotations

import time
from typing import Dict, List, Optional, Tuple

import structlog

from app.ai_models.qa_model import get_qa_model
from app.services.embedding_service import EmbeddingService
from app.database.prisma_client import get_db

logger = structlog.get_logger()


class RAGService:
    """
    Production RAG pipeline for research paper Q&A.
    
    Pipeline:
    1. Embed the user question
    2. Retrieve top-k relevant chunks via vector similarity
    3. Re-rank chunks by relevance
    4. Pass best chunks as context to QA model
    5. Return structured answer with citations
    """

    def __init__(self):
        self.embedding_service = EmbeddingService()
        self.qa_model = get_qa_model()
        self.db = get_db()

    async def ask(
        self,
        question: str,
        paper_id: Optional[str] = None,
        paper_ids: Optional[List[str]] = None,
        top_k: int = 5,
        include_context: bool = True,
    ) -> Dict:
        """
        Full RAG pipeline: retrieve relevant chunks and generate an answer.

        Args:
            question: User question.
            paper_id: Single paper to search in.
            paper_ids: Multiple papers to search across.
            top_k: Number of chunks to retrieve.
            include_context: Whether to include source chunks in response.

        Returns:
            Dict with answer, confidence, sources, and metadata.
        """
        start_time = time.time()

        # Determine paper scope
        search_paper_ids = None
        if paper_id:
            search_paper_ids = [paper_id]
        elif paper_ids:
            search_paper_ids = paper_ids

        # Step 1 & 2: Retrieve relevant chunks
        # Use a very low threshold — let the re-ranker and QA model
        # decide what is actually relevant.
        search_results = await self.embedding_service.semantic_search(
            query=question,
            top_k=top_k * 2,  # Retrieve more, then re-rank
            paper_ids=search_paper_ids,
            threshold=0.05,
        )

        if not search_results:
            return {
                "answer": "I couldn't find relevant information in the paper(s) to answer your question. Please try rephrasing or ask about a different topic.",
                "confidence": 0.0,
                "sources": [],
                "tokens_used": 0,
                "response_time": round(time.time() - start_time, 3),
            }

        # Step 3: Re-rank and select top chunks
        ranked_chunks = self._rerank_chunks(question, search_results, top_k)

        # Step 4: Build context and generate answer
        context_chunks = [(chunk["chunk_text"], chunk["similarity"]) for chunk in ranked_chunks]

        # Build combined context for QA
        combined_context = self._build_context(ranked_chunks)

        # Get answer from QA model
        qa_result = self.qa_model.answer_from_chunks(
            question=question,
            chunks=context_chunks,
            top_k=3,
        )

        # Step 5: Build response with sources
        sources = []
        if include_context:
            for chunk in ranked_chunks:
                sources.append({
                    "chunk_text": chunk["chunk_text"],
                    "paper_id": chunk["paper_id"],
                    "paper_title": chunk.get("paper_title", ""),
                    "chunk_index": chunk["chunk_index"],
                    "similarity": chunk["similarity"],
                    "section": chunk.get("section"),
                })

        response_time = round(time.time() - start_time, 3)

        result = {
            "answer": qa_result["answer"],
            "confidence": qa_result["confidence"],
            "sources": sources,
            "supporting_evidence": qa_result.get("supporting_evidence", []),
            "tokens_used": self._estimate_tokens(combined_context + question),
            "response_time": response_time,
        }

        logger.info(
            "rag_answer_generated",
            question_len=len(question),
            chunks_used=len(ranked_chunks),
            confidence=qa_result["confidence"],
            time=response_time,
        )

        return result

    async def multi_paper_ask(
        self,
        question: str,
        paper_ids: List[str],
        top_k: int = 5,
    ) -> Dict:
        """Ask a question across multiple papers with comparative analysis."""
        return await self.ask(
            question=question,
            paper_ids=paper_ids,
            top_k=top_k,
            include_context=True,
        )

    def _rerank_chunks(
        self,
        question: str,
        chunks: List[Dict],
        top_k: int,
    ) -> List[Dict]:
        """
        Re-rank retrieved chunks for better relevance.
        Uses a combination of semantic similarity and keyword overlap.
        """
        question_words = set(question.lower().split())

        for chunk in chunks:
            chunk_words = set(chunk["chunk_text"].lower().split())
            keyword_overlap = len(question_words & chunk_words) / max(len(question_words), 1)

            # Combined score: 70% semantic + 30% keyword
            chunk["rerank_score"] = (chunk["similarity"] * 0.7) + (keyword_overlap * 0.3)

        # Sort by re-rank score
        chunks.sort(key=lambda x: x["rerank_score"], reverse=True)

        return chunks[:top_k]

    def _build_context(self, chunks: List[Dict], max_tokens: int = 2000) -> str:
        """Build a context string from chunks within token limit."""
        context_parts = []
        total_tokens = 0

        for chunk in chunks:
            chunk_tokens = chunk.get("token_count", len(chunk["chunk_text"].split()))
            if total_tokens + chunk_tokens > max_tokens:
                break
            context_parts.append(chunk["chunk_text"])
            total_tokens += chunk_tokens

        return "\n\n".join(context_parts)

    def _estimate_tokens(self, text: str) -> int:
        """Rough token count estimation."""
        return int(len(text.split()) * 1.3)


def get_rag_service() -> RAGService:
    return RAGService()
