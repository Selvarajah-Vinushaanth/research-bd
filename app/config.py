# ============================================
# AI Research Assistant - Application Configuration
# ============================================

from __future__ import annotations

import os
from functools import lru_cache
from typing import List, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""

    # --- Application ---
    APP_NAME: str = "AI Research Assistant"
    APP_VERSION: str = "1.0.0"
    APP_ENV: str = "development"
    DEBUG: bool = True
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    ALLOWED_ORIGINS: str = "http://localhost:3000,http://localhost:8080"
    API_V1_PREFIX: str = "/api/v1"

    # --- Database ---
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/research_assistant"

    # --- Redis ---
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379

    # --- JWT ---
    JWT_SECRET_KEY: str = "change-this-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # --- Google Cloud ---
    GCP_PROJECT_ID: str = ""
    GCP_BUCKET_NAME: str = "research-assistant-papers"
    GCP_CREDENTIALS_PATH: str = ""

    # --- AI Models ---
    EMBEDDING_MODEL: str = "sentence-transformers/all-MiniLM-L6-v2"
    SUMMARIZER_MODEL: str = "facebook/bart-large-cnn"
    QA_MODEL: str = "deepset/roberta-base-squad2"
    GENERATIVE_MODEL: str = "Qwen/Qwen2.5-72B-Instruct"
    EMBEDDING_DIMENSION: int = 384

    # --- Hugging Face Inference API ---
    HUGGINGFACE_API_TOKEN: str = ""

    # --- Celery ---
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"

    # --- Sentry ---
    SENTRY_DSN: str = ""

    # --- Rate Limiting ---
    RATE_LIMIT_PER_MINUTE: int = 60

    # --- File Upload ---
    MAX_UPLOAD_SIZE_MB: int = 50
    ALLOWED_FILE_TYPES: str = ".pdf"

    # --- Chunking ---
    CHUNK_SIZE: int = 500
    CHUNK_OVERLAP: int = 50

    # --- Caching ---
    CACHE_TTL_SECONDS: int = 3600
    CACHE_PREFIX: str = "research_assistant"

    # --- Google reCAPTCHA ---
    RECAPTCHA_SECRET_KEY: str = ""
    RECAPTCHA_ENABLED: bool = True
    RECAPTCHA_MIN_SCORE: float = 0.5  # For reCAPTCHA v3 (score-based)

    @property
    def allowed_origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",")]

    @property
    def max_upload_bytes(self) -> int:
        return self.MAX_UPLOAD_SIZE_MB * 1024 * 1024

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True
        extra = "ignore"  # Allow extra env vars


@lru_cache()
def get_settings() -> Settings:
    """Cache and return application settings singleton."""
    return Settings()


settings = get_settings()
