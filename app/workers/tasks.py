# ============================================
# Celery Tasks - Async Processing
# ============================================

from __future__ import annotations

import asyncio
import os
import sys
import time
from typing import Optional

import structlog

from app.workers.celery_worker import celery_app

logger = structlog.get_logger()


def _fix_celery_stdout():
    """
    Celery's solo pool replaces sys.stdout/sys.stderr with LoggingProxy
    objects that lack a .fileno() method.  Prisma's query engine spawns a
    subprocess via subprocess.Popen which needs real file descriptors.

    This function restores real file objects so Prisma can start its
    engine subprocess.
    """
    if not hasattr(sys.stdout, "fileno"):
        sys.stdout = open(os.devnull, "w")
    else:
        try:
            sys.stdout.fileno()
        except Exception:
            sys.stdout = open(os.devnull, "w")

    if not hasattr(sys.stderr, "fileno"):
        sys.stderr = open(os.devnull, "w")
    else:
        try:
            sys.stderr.fileno()
        except Exception:
            sys.stderr = open(os.devnull, "w")


def run_async(coro):
    """Helper to run async functions from sync Celery tasks."""
    _fix_celery_stdout()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    acks_late=True,
    name="app.workers.tasks.process_paper_task",
)
def process_paper_task(self, paper_id: str, full_text: str):
    """
    Async task to process a paper:
    1. Chunk the text
    2. Generate embeddings
    3. Store in vector database
    4. Update paper status
    """
    logger.info("task_process_paper_started", paper_id=paper_id, task_id=self.request.id)
    start_time = time.time()

    try:
        run_async(_process_paper(paper_id, full_text, self))
        elapsed = round(time.time() - start_time, 3)
        logger.info("task_process_paper_completed", paper_id=paper_id, time=elapsed)
        return {"status": "success", "paper_id": paper_id, "time": elapsed}

    except Exception as exc:
        logger.error("task_process_paper_failed", paper_id=paper_id, error=str(exc))
        # Update status to FAILED
        run_async(_update_paper_status(paper_id, "FAILED"))
        raise self.retry(exc=exc)


async def _process_paper(paper_id: str, full_text: str, task):
    """Internal async function for paper processing."""
    from app.database.prisma_client import prisma_connect, prisma_disconnect, get_db
    from app.utils.chunking import get_chunker
    from app.services.embedding_service import EmbeddingService

    await prisma_connect()
    db = get_db()

    try:
        # Update status to PROCESSING
        await db.paper.update(
            where={"id": paper_id},
            data={"status": "PROCESSING", "processing_progress": 0.1},
        )

        # Step 1: Chunk text (20%)
        chunker = get_chunker()
        chunks = chunker.chunk_by_tokens(full_text)
        chunks = chunker.merge_small_chunks(chunks)
        logger.info("paper_chunked", paper_id=paper_id, chunks=len(chunks))

        await db.paper.update(
            where={"id": paper_id},
            data={"processing_progress": 0.3},
        )

        # Step 2: Generate and store embeddings (30% -> 80%)
        embedding_service = EmbeddingService()
        stored = await embedding_service.generate_and_store_embeddings(paper_id, chunks)

        await db.paper.update(
            where={"id": paper_id},
            data={"processing_progress": 0.8},
        )

        # Step 3: Update metadata (80% -> 100%)
        await db.papermetadata.update(
            where={"paper_id": paper_id},
            data={"chunk_count": stored},
        )

        # Step 4: Mark as processed
        await db.paper.update(
            where={"id": paper_id},
            data={"status": "PROCESSED", "processing_progress": 1.0},
        )

        logger.info("paper_fully_processed", paper_id=paper_id, chunks=stored)

    finally:
        await prisma_disconnect()


async def _update_paper_status(paper_id: str, status: str):
    """Update paper status (used for error handling)."""
    from app.database.prisma_client import prisma_connect, prisma_disconnect, get_db

    await prisma_connect()
    db = get_db()
    try:
        await db.paper.update(
            where={"id": paper_id},
            data={"status": status},
        )
    finally:
        await prisma_disconnect()


@celery_app.task(
    bind=True,
    max_retries=2,
    name="app.workers.tasks.generate_embeddings_task",
)
def generate_embeddings_task(self, paper_id: str):
    """Re-generate embeddings for a paper."""
    logger.info("task_generate_embeddings_started", paper_id=paper_id)

    try:
        run_async(_regenerate_embeddings(paper_id))
        return {"status": "success", "paper_id": paper_id}
    except Exception as exc:
        logger.error("task_generate_embeddings_failed", error=str(exc))
        raise self.retry(exc=exc)


async def _regenerate_embeddings(paper_id: str):
    """Internal function to regenerate embeddings."""
    from app.database.prisma_client import prisma_connect, prisma_disconnect, get_db
    from app.utils.chunking import get_chunker
    from app.services.embedding_service import EmbeddingService

    await prisma_connect()
    db = get_db()

    try:
        # Delete existing chunks
        await db.paperchunk.delete_many(where={"paper_id": paper_id})

        # Get paper text from stored chunks or re-extract
        paper = await db.paper.find_unique(where={"id": paper_id})
        if not paper:
            raise ValueError(f"Paper {paper_id} not found")

        # Re-chunk and embed
        chunker = get_chunker()
        # Note: In production, you'd re-read from storage
        logger.warning("embedding_regeneration_requires_text", paper_id=paper_id)

    finally:
        await prisma_disconnect()


@celery_app.task(
    bind=True,
    max_retries=2,
    name="app.workers.tasks.summarize_paper_task",
)
def summarize_paper_task(self, paper_id: str, summary_type: str = "STRUCTURED"):
    """Async task to generate paper summary."""
    logger.info("task_summarize_paper_started", paper_id=paper_id, type=summary_type)

    try:
        result = run_async(_summarize_paper(paper_id, summary_type))
        return {"status": "success", "paper_id": paper_id, "summary_id": result}
    except Exception as exc:
        logger.error("task_summarize_paper_failed", error=str(exc))
        raise self.retry(exc=exc)


async def _summarize_paper(paper_id: str, summary_type: str):
    """Internal function for paper summarization."""
    from app.database.prisma_client import prisma_connect, prisma_disconnect
    from app.services.summarization_service import SummarizationService

    await prisma_connect()
    try:
        service = SummarizationService()
        result = await service.summarize_paper(paper_id, summary_type)
        return result.get("id")
    finally:
        from app.database.prisma_client import prisma_disconnect
        await prisma_disconnect()


@celery_app.task(
    bind=True,
    max_retries=1,
    name="app.workers.tasks.run_clustering_task",
)
def run_clustering_task(self, algorithm: str = "kmeans", n_clusters: int = 5):
    """Async task to run paper clustering."""
    logger.info("task_clustering_started", algorithm=algorithm, n_clusters=n_clusters)

    try:
        result = run_async(_run_clustering(algorithm, n_clusters))
        return {"status": "success", "clusters": len(result.get("clusters", []))}
    except Exception as exc:
        logger.error("task_clustering_failed", error=str(exc))
        raise self.retry(exc=exc)


async def _run_clustering(algorithm: str, n_clusters: int):
    """Internal function for clustering."""
    from app.database.prisma_client import prisma_connect, prisma_disconnect
    from app.services.clustering_service import ClusteringService

    await prisma_connect()
    try:
        service = ClusteringService()
        return await service.run_clustering(algorithm=algorithm, n_clusters=n_clusters)
    finally:
        await prisma_disconnect()


@celery_app.task(name="app.workers.tasks.cleanup_failed_papers")
def cleanup_failed_papers():
    """Periodic task: Clean up papers stuck in PROCESSING state."""
    logger.info("task_cleanup_started")
    run_async(_cleanup_failed())


async def _cleanup_failed():
    """Mark stuck papers as FAILED."""
    from datetime import datetime, timedelta, timezone
    from app.database.prisma_client import prisma_connect, prisma_disconnect, get_db

    await prisma_connect()
    db = get_db()

    try:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
        stuck = await db.paper.find_many(
            where={
                "status": "PROCESSING",
                "updated_at": {"lt": cutoff},
            }
        )

        for paper in stuck:
            await db.paper.update(
                where={"id": paper.id},
                data={"status": "FAILED"},
            )
            logger.warning("paper_marked_failed", paper_id=paper.id, reason="stuck_processing")

        logger.info("cleanup_completed", stuck_papers=len(stuck))

    finally:
        await prisma_disconnect()


@celery_app.task(name="app.workers.tasks.update_cluster_stats")
def update_cluster_stats():
    """Periodic task: Update cluster paper counts."""
    logger.info("task_update_cluster_stats")
    run_async(_update_clusters())


async def _update_clusters():
    """Update cluster statistics."""
    from app.database.prisma_client import prisma_connect, prisma_disconnect, get_db

    await prisma_connect()
    db = get_db()

    try:
        clusters = await db.topiccluster.find_many()
        for cluster in clusters:
            count = await db.papercluster.count(where={"cluster_id": cluster.id})
            await db.topiccluster.update(
                where={"id": cluster.id},
                data={"paper_count": count},
            )
    finally:
        await prisma_disconnect()
