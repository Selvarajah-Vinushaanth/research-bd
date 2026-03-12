# ============================================
# AI Models - Summarization Model (HuggingFace Hub InferenceClient)
# ============================================

from __future__ import annotations

import os
import threading
import time
from typing import Dict, List, Optional

import structlog
from huggingface_hub import InferenceClient

from app.config import settings

# Ensure HF SDK picks up the token for all internal HTTP calls
_hf_token = settings.HUGGINGFACE_API_TOKEN
if _hf_token and not os.environ.get("HF_TOKEN"):
    os.environ["HF_TOKEN"] = _hf_token

logger = structlog.get_logger()


class SummarizerModel:
    """
    Thread-safe singleton for text summarization via the official
    huggingface_hub InferenceClient using ``facebook/bart-large-cnn``.

    No local model download required.
    """

    _instance: Optional[SummarizerModel] = None
    _lock = threading.Lock()

    def __new__(cls) -> SummarizerModel:
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
        self._model_name = settings.SUMMARIZER_MODEL
        self._client = InferenceClient(
            token=settings.HUGGINGFACE_API_TOKEN or None,
            timeout=30,
        )
        logger.info("summarizer_model_init_hf_client", model=self._model_name)

    def summarize(
        self,
        text: str,
        max_length: int = 300,
        min_length: int = 80,
        do_sample: bool = False,
    ) -> str:
        """
        Generate a summary of the given text via HF Inference Providers.

        Args:
            text: Input text to summarize.
            max_length: Maximum summary length in tokens.
            min_length: Minimum summary length in tokens.
            do_sample: (ignored – kept for interface compat).

        Returns:
            Summary text string.
        """
        text = text.strip()

        # Clean text of special characters that break BART tokenization
        import re
        import unicodedata
        text = unicodedata.normalize("NFKD", text)
        # Strip accents / combining marks
        text = "".join(
            c for c in text
            if unicodedata.category(c) not in ("Mn", "Mc", "Me")  # combining marks
            and unicodedata.category(c)[0] != "C"                  # control chars
            or c in "\n\t "
        )
        # Keep only printable ASCII + basic punctuation + common unicode
        text = re.sub(r"[^\x20-\x7E\n\t]+", " ", text)
        # Collapse excessive whitespace
        text = re.sub(r"\s+", " ", text).strip()

        words = text.split()

        # Text too short for BART – return as-is
        if len(words) < 40:
            logger.debug("text_too_short_for_summary", word_count=len(words))
            return text

        # BART has a max positional embedding of 1024 tokens.
        # Non-prose text (CVs, lists, URLs) can generate 2-3 tokens/word.
        # Safe limit: 400 words ≈ ~800 tokens worst case
        if len(words) > 400:
            text = " ".join(words[:400])

        # Clamp min_length so it doesn't exceed input length
        min_length = min(min_length, max(10, len(words) // 4))

        try:
            max_retries = 3
            result = None
            for attempt in range(max_retries):
                try:
                    result = self._client.summarization(
                        text,
                        model=self._model_name,
                    )
                    break
                except Exception as retry_err:
                    if "429" in str(retry_err) and attempt < max_retries - 1:
                        wait = 2 ** (attempt + 1)
                        logger.warning("hf_summarize_rate_limited_retrying", attempt=attempt + 1, wait=wait)
                        time.sleep(wait)
                        continue
                    raise

            # result is a SummarizationOutput with .summary_text
            summary = result.summary_text if hasattr(result, "summary_text") else str(result)

            logger.debug(
                "summary_generated", input_len=len(text), output_len=len(summary)
            )
            return summary

        except Exception as e:
            logger.warning("summarization_api_error", error=str(e), input_len=len(text))
            # Fallback: return first ~max_length words of the text
            fallback = " ".join(words[: max(50, max_length // 3)])
            if len(fallback) < len(text):
                fallback += "..."
            return fallback

    def summarize_sections(self, sections: Dict[str, str]) -> Dict[str, str]:
        """
        Summarize individual sections of a paper.

        Args:
            sections: Dict mapping section names to text content.

        Returns:
            Dict mapping section names to summaries.
        """
        summaries = {}
        for section_name, text in sections.items():
            if text and len(text.strip()) > 50:
                try:
                    summaries[section_name] = self.summarize(
                        text, max_length=200, min_length=40
                    )
                except Exception as e:
                    logger.warning(
                        "section_summarization_failed",
                        section=section_name,
                        error=str(e),
                    )
                    summaries[section_name] = text[:500] + "..."
            else:
                summaries[section_name] = text or ""
        return summaries

    def summarize_long_document(
        self, text: str, chunk_size: int = 350, max_length: int = 500
    ) -> str:
        """
        Summarize a long document using hierarchical summarization.
        Splits into chunks, summarizes each, then summarizes the summaries.
        """
        words = text.split()
        if len(words) <= 400:
            return self.summarize(text, max_length=max_length)

        # Split into chunks (cap at 6 to keep API calls manageable)
        chunks = []
        for i in range(0, len(words), chunk_size):
            chunk = " ".join(words[i : i + chunk_size])
            chunks.append(chunk)
        if len(chunks) > 6:
            chunks = chunks[:6]

        # Summarize each chunk
        chunk_summaries = []
        for chunk in chunks:
            try:
                summary = self.summarize(chunk, max_length=150, min_length=30)
                chunk_summaries.append(summary)
            except Exception as e:
                logger.warning("chunk_summarization_failed", error=str(e))
                continue

        if not chunk_summaries:
            # All chunks failed – return truncated original text
            return " ".join(words[:200]) + "..."

        # Combine and re-summarize
        combined = " ".join(chunk_summaries)
        if len(combined.split()) > 900:
            return self.summarize(combined, max_length=max_length, min_length=100)

        return self.summarize(combined, max_length=max_length, min_length=100)


def get_summarizer_model() -> SummarizerModel:
    return SummarizerModel()
