# ============================================
# Celery Worker Configuration
# ============================================

from __future__ import annotations

from celery import Celery

from app.config import settings

# Create Celery app
celery_app = Celery(
    "research_assistant",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["app.workers.tasks"],
)

# Celery configuration
celery_app.conf.update(
    # Task settings
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,

    # Redis SSL configuration for rediss:// URLs
    redis_socket_keepalive=True,
    redis_socket_keepalive_options={},
    redis_ssl_cert_reqs="none",

    # Worker settings
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=50,
    worker_max_memory_per_child=512000,  # 512MB

    # Task routing – disabled by default so the dev solo worker picks
    # up every task from the default "celery" queue.  In production,
    # uncomment and run dedicated workers with: celery -Q paper_processing
    # task_routes={
    #     "app.workers.tasks.process_paper_task":    {"queue": "paper_processing"},
    #     "app.workers.tasks.generate_embeddings_task": {"queue": "embedding"},
    #     "app.workers.tasks.summarize_paper_task":  {"queue": "ai_tasks"},
    #     "app.workers.tasks.run_clustering_task":   {"queue": "ai_tasks"},
    # },

    # Rate limiting
    task_default_rate_limit="10/m",

    # Result expiry
    result_expires=3600,

    # Retry settings
    task_acks_late=True,
    task_reject_on_worker_lost=True,

    # Beat schedule (periodic tasks)
    beat_schedule={
        "cleanup-failed-papers": {
            "task": "app.workers.tasks.cleanup_failed_papers",
            "schedule": 3600.0,  # Every hour
        },
        "update-cluster-stats": {
            "task": "app.workers.tasks.update_cluster_stats",
            "schedule": 86400.0,  # Every 24 hours
        },
    },
)
