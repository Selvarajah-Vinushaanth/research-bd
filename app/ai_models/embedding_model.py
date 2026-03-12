# ============================================
# AI Models - Embedding Model (HuggingFace Hub InferenceClient)
# ============================================

from __future__ import annotations

import os
import threading
import time
from typing import List, Optional

import numpy as np
import structlog
from huggingface_hub import InferenceClient

from app.config import settings

# Ensure HF SDK picks up the token for all internal HTTP calls
_hf_token = settings.HUGGINGFACE_API_TOKEN
if _hf_token and not os.environ.get("HF_TOKEN"):
    os.environ["HF_TOKEN"] = _hf_token

logger = structlog.get_logger()


class EmbeddingModel:
    """
    Thread-safe singleton that generates embeddings via the official
    huggingface_hub InferenceClient.

    Uses ``sentence-transformers/all-MiniLM-L6-v2`` through HF Inference
    Providers — no local model download needed.
    """

    _instance: Optional[EmbeddingModel] = None
    _lock = threading.Lock()

    def __new__(cls) -> EmbeddingModel:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self._initialized = True
        self._model_name = settings.EMBEDDING_MODEL
        self._dimension = settings.EMBEDDING_DIMENSION
        self._client = InferenceClient(
            token=settings.HUGGINGFACE_API_TOKEN or None,
        )
        logger.info(
            "embedding_model_init_hf_client",
            model=self._model_name,
            dim=self._dimension,
        )

    @property
    def dimension(self) -> int:
        return self._dimension

    def _embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Call HF Inference Providers for feature extraction with retry."""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                results = self._client.feature_extraction(
                    texts,
                    model=self._model_name,
                )
                # The SDK returns an np.ndarray or nested list.
                # Ensure we always work with a list-of-lists.
                if isinstance(results, np.ndarray):
                    return results.tolist()
                return results
            except Exception as e:
                if "429" in str(e) and attempt < max_retries - 1:
                    wait = 2 ** (attempt + 1)
                    logger.warning("hf_rate_limited_retrying", attempt=attempt + 1, wait=wait)
                    time.sleep(wait)
                    continue
                raise

    def encode(
        self,
        texts: List[str],
        batch_size: int = 64,
        normalize: bool = True,
        show_progress: bool = False,
    ) -> np.ndarray:
        """
        Encode a list of texts into embeddings via HF Inference Providers.

        Args:
            texts: List of text strings to encode.
            batch_size: Batch size for API calls.
            normalize: Whether to L2-normalize embeddings.
            show_progress: (ignored – kept for interface compat).

        Returns:
            NumPy array of shape (n_texts, dimension).
        """
        all_embeddings: List[List[float]] = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            result = self._embed_batch(batch)
            all_embeddings.extend(result)

        embeddings = np.array(all_embeddings, dtype=np.float32)

        # Handle 3-D output (token-level) → mean-pool to sentence-level
        if embeddings.ndim == 3:
            embeddings = embeddings.mean(axis=1)

        if normalize:
            norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
            norms[norms == 0] = 1
            embeddings = embeddings / norms

        logger.debug("embeddings_generated", count=len(texts), shape=embeddings.shape)
        return embeddings

    def encode_single(self, text: str, normalize: bool = True) -> List[float]:
        """Encode a single text and return as a list of floats."""
        embedding = self.encode([text], normalize=normalize)
        return embedding[0].tolist()

    def similarity(self, text_a: str, text_b: str) -> float:
        """Compute cosine similarity between two texts."""
        embeddings = self.encode([text_a, text_b], normalize=True)
        return float(np.dot(embeddings[0], embeddings[1]))

    def batch_similarity(self, query: str, documents: List[str]) -> List[float]:
        """Compute similarities between a query and multiple documents."""
        all_texts = [query] + documents
        embeddings = self.encode(all_texts, normalize=True)
        query_emb = embeddings[0]
        doc_embs = embeddings[1:]
        similarities = np.dot(doc_embs, query_emb).tolist()
        return similarities


# Module-level singleton access
def get_embedding_model() -> EmbeddingModel:
    return EmbeddingModel()
