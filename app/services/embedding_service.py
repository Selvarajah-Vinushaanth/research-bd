# ============================================
# Service - Embedding Generation & Vector Search
# ============================================

from __future__ import annotations

import time
from typing import Dict, List, Optional, Tuple

import numpy as np
import structlog

from app.ai_models.embedding_model import get_embedding_model
from app.database.prisma_client import get_db
from app.config import settings

logger = structlog.get_logger()


class EmbeddingService:
    """
    Service for generating embeddings and performing vector similarity search.
    Interfaces with pgvector for storage and retrieval.
    """

    def __init__(self):
        self.model = get_embedding_model()
        self.db = get_db()

    async def generate_and_store_embeddings(
        self,
        paper_id: str,
        chunks: List[dict],
        batch_size: int = 64,
    ) -> int:
        """
        Generate embeddings for paper chunks and store in database.

        Args:
            paper_id: The paper ID.
            chunks: List of chunk dicts with 'text', 'index', 'token_count', 'section'.
            batch_size: Batch size for embedding generation.

        Returns:
            Number of embeddings stored.
        """
        start_time = time.time()
        texts = [chunk["text"] for chunk in chunks]

        # Generate embeddings in batches
        logger.info("generating_embeddings", paper_id=paper_id, chunks=len(texts))
        embeddings = self.model.encode(texts, batch_size=batch_size)

        # Store each chunk with its embedding
        stored_count = 0
        for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
            embedding_list = embedding.tolist()
            embedding_str = "[" + ",".join(str(x) for x in embedding_list) + "]"

            try:
                await self.db.execute_raw(
                    """
                    INSERT INTO paper_chunks (id, paper_id, chunk_index, chunk_text, token_count, section, embedding, created_at)
                    VALUES (gen_random_uuid(), $1, $2, $3, $4, $5, $6::vector, NOW())
                    """,
                    paper_id,
                    chunk["index"],
                    chunk["text"],
                    chunk.get("token_count", 0),
                    chunk.get("section"),
                    embedding_str,
                )
                stored_count += 1
            except Exception as e:
                logger.error(
                    "embedding_store_failed",
                    paper_id=paper_id,
                    chunk_index=i,
                    error=str(e),
                )

        elapsed = time.time() - start_time
        logger.info(
            "embeddings_stored",
            paper_id=paper_id,
            stored=stored_count,
            total=len(chunks),
            time=round(elapsed, 3),
        )
        return stored_count

    async def semantic_search(
        self,
        query: str,
        top_k: int = 10,
        paper_ids: Optional[List[str]] = None,
        threshold: float = 0.5,
        user_id: Optional[str] = None,
    ) -> List[Dict]:
        """
        Perform semantic similarity search across paper chunks.

        Args:
            query: Search query text.
            top_k: Number of top results to return.
            paper_ids: Optional list of paper IDs to restrict search.
            threshold: Minimum similarity threshold.

        Returns:
            List of result dicts with chunk info and similarity scores.
        """
        # Generate query embedding
        query_embedding = self.model.encode_single(query)
        embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"

        # Build SQL query with optional paper_id filter
        if paper_ids and user_id:
            placeholders = ",".join(f"${i+3}" for i in range(len(paper_ids)))
            results = await self.db.query_raw(
                f"""
                SELECT
                    pc.id,
                    pc.paper_id,
                    pc.chunk_index,
                    pc.chunk_text,
                    pc.section,
                    pc.token_count,
                    1 - (pc.embedding <=> $1::vector) as similarity,
                    p.title as paper_title
                FROM paper_chunks pc
                JOIN papers p ON pc.paper_id = p.id
                WHERE pc.paper_id IN ({placeholders})
                    AND pc.embedding IS NOT NULL
                    AND p.uploaded_by = $2
                ORDER BY pc.embedding <=> $1::vector
                LIMIT {top_k}
                """,
                embedding_str,
                user_id,
                *paper_ids,
            )
        elif paper_ids:
            placeholders = ",".join(f"${i+2}" for i in range(len(paper_ids)))
            results = await self.db.query_raw(
                f"""
                SELECT
                    pc.id,
                    pc.paper_id,
                    pc.chunk_index,
                    pc.chunk_text,
                    pc.section,
                    pc.token_count,
                    1 - (pc.embedding <=> $1::vector) as similarity,
                    p.title as paper_title
                FROM paper_chunks pc
                JOIN papers p ON pc.paper_id = p.id
                WHERE pc.paper_id IN ({placeholders})
                    AND pc.embedding IS NOT NULL
                ORDER BY pc.embedding <=> $1::vector
                LIMIT {top_k}
                """,
                embedding_str,
                *paper_ids,
            )
        elif user_id:
            # Scope to current user's papers only
            results = await self.db.query_raw(
                f"""
                SELECT
                    pc.id,
                    pc.paper_id,
                    pc.chunk_index,
                    pc.chunk_text,
                    pc.section,
                    pc.token_count,
                    1 - (pc.embedding <=> $1::vector) as similarity,
                    p.title as paper_title
                FROM paper_chunks pc
                JOIN papers p ON pc.paper_id = p.id
                WHERE pc.embedding IS NOT NULL
                    AND p.uploaded_by = $2
                ORDER BY pc.embedding <=> $1::vector
                LIMIT {top_k}
                """,
                embedding_str,
                user_id,
            )
        else:
            results = await self.db.query_raw(
                f"""
                SELECT
                    pc.id,
                    pc.paper_id,
                    pc.chunk_index,
                    pc.chunk_text,
                    pc.section,
                    pc.token_count,
                    1 - (pc.embedding <=> $1::vector) as similarity,
                    p.title as paper_title
                FROM paper_chunks pc
                JOIN papers p ON pc.paper_id = p.id
                WHERE pc.embedding IS NOT NULL
                ORDER BY pc.embedding <=> $1::vector
                LIMIT {top_k}
                """,
                embedding_str,
            )

        # Filter by threshold and format results
        search_results = []
        for row in results:
            sim = float(row.get("similarity", 0))
            if sim >= threshold:
                search_results.append({
                    "id": row["id"],
                    "paper_id": row["paper_id"],
                    "paper_title": row.get("paper_title", ""),
                    "chunk_text": row["chunk_text"],
                    "chunk_index": row["chunk_index"],
                    "section": row.get("section"),
                    "token_count": row.get("token_count", 0),
                    "similarity": round(sim, 4),
                })

        logger.info(
            "semantic_search_completed",
            query_len=len(query),
            results=len(search_results),
            top_similarity=search_results[0]["similarity"] if search_results else 0,
        )

        return search_results

    async def find_related_papers(
        self,
        paper_id: str,
        top_k: int = 10,
        user_id: Optional[str] = None,
    ) -> List[Dict]:
        """
        Find papers related to a given paper using average embedding similarity.
        """
        # Get average embedding for the source paper
        avg_result = await self.db.query_raw(
            """
            SELECT AVG(embedding)::text as avg_embedding
            FROM paper_chunks
            WHERE paper_id = $1 AND embedding IS NOT NULL
            """,
            paper_id,
        )

        if not avg_result or not avg_result[0].get("avg_embedding"):
            return []

        avg_embedding = avg_result[0]["avg_embedding"]

        # Find similar papers (excluding the source, scoped to user)
        if user_id:
            results = await self.db.query_raw(
                f"""
                SELECT
                    p.id as paper_id,
                    p.title,
                    p.authors,
                    AVG(1 - (pc.embedding <=> $1::vector)) as avg_similarity
                FROM paper_chunks pc
                JOIN papers p ON pc.paper_id = p.id
                WHERE pc.paper_id != $2
                    AND pc.embedding IS NOT NULL
                    AND p.uploaded_by = $3
                GROUP BY p.id, p.title, p.authors
                ORDER BY avg_similarity DESC
                LIMIT {top_k}
                """,
                avg_embedding,
                paper_id,
                user_id,
            )
        else:
            results = await self.db.query_raw(
                f"""
                SELECT
                    p.id as paper_id,
                    p.title,
                    p.authors,
                    AVG(1 - (pc.embedding <=> $1::vector)) as avg_similarity
                FROM paper_chunks pc
                JOIN papers p ON pc.paper_id = p.id
                WHERE pc.paper_id != $2
                    AND pc.embedding IS NOT NULL
                GROUP BY p.id, p.title, p.authors
                ORDER BY avg_similarity DESC
                LIMIT {top_k}
                """,
                avg_embedding,
                paper_id,
            )

        related = []
        for row in results:
            related.append({
                "paper_id": row["paper_id"],
                "title": row["title"],
                "authors": row.get("authors", []),
                "similarity": round(float(row.get("avg_similarity", 0)), 4),
            })

        return related

    async def get_paper_embedding_stats(self, paper_id: str) -> Dict:
        """Get embedding statistics for a paper."""
        result = await self.db.query_raw(
            """
            SELECT
                COUNT(*) as chunk_count,
                COUNT(embedding) as embedded_count,
                AVG(token_count) as avg_tokens
            FROM paper_chunks
            WHERE paper_id = $1
            """,
            paper_id,
        )

        if result:
            return {
                "chunk_count": int(result[0].get("chunk_count", 0)),
                "embedded_count": int(result[0].get("embedded_count", 0)),
                "avg_tokens": round(float(result[0].get("avg_tokens", 0)), 1),
            }
        return {"chunk_count": 0, "embedded_count": 0, "avg_tokens": 0}


def get_embedding_service() -> EmbeddingService:
    return EmbeddingService()
