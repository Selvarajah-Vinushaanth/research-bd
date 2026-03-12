# ============================================
# AI Models - Question Answering (Generative + Extractive)
# ============================================

from __future__ import annotations

import os
import threading
import time
from typing import Dict, List, Optional, Tuple

import structlog
from huggingface_hub import InferenceClient

from app.config import settings

# Ensure HF SDK picks up the token for all internal HTTP calls
_hf_token = settings.HUGGINGFACE_API_TOKEN
if _hf_token and not os.environ.get("HF_TOKEN"):
    os.environ["HF_TOKEN"] = _hf_token

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Generative model used for producing rich, structured answers.
# We keep the extractive model as a fast fallback.
# ---------------------------------------------------------------------------
_GENERATIVE_MODEL = "Qwen/Qwen2.5-72B-Instruct"


class QAModel:
    """
    Thread-safe singleton for research-paper question answering.

    **Primary path** – generative:
        Uses a large instruct-tuned LLM (Mistral-7B-Instruct) via the
        HuggingFace Inference API ``chat_completion`` endpoint to produce
        detailed, Markdown-formatted answers like ChatGPT / Claude.

    **Fallback** – extractive:
        If the generative call fails (cold-start timeout, quota, etc.) we
        fall back to ``deepset/roberta-base-squad2`` extractive QA so the
        user still gets *something*.
    """

    _instance: Optional[QAModel] = None
    _lock = threading.Lock()

    def __new__(cls) -> QAModel:
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
        self._extractive_model = settings.QA_MODEL
        self._generative_model = getattr(settings, "GENERATIVE_MODEL", _GENERATIVE_MODEL)
        self._client = InferenceClient(
            token=settings.HUGGINGFACE_API_TOKEN or None,
        )
        logger.info(
            "qa_model_init",
            generative=self._generative_model,
            extractive=self._extractive_model,
        )

    # --------------------------------------------------------------------- #
    # Public API
    # --------------------------------------------------------------------- #

    def answer(
        self,
        question: str,
        context: str,
        top_k: int = 3,
    ) -> List[Dict]:
        """Extractive QA – kept for backward compatibility / fallback."""
        if not context or not question:
            return [{"answer": "No context available.", "score": 0.0}]

        try:
            max_retries = 3
            result = None
            for attempt in range(max_retries):
                try:
                    result = self._client.question_answering(
                        question=question,
                        context=context,
                        model=self._extractive_model,
                    )
                    break
                except Exception as retry_err:
                    if "429" in str(retry_err) and attempt < max_retries - 1:
                        wait = 2 ** (attempt + 1)
                        logger.warning("hf_qa_rate_limited_retrying", attempt=attempt + 1, wait=wait)
                        time.sleep(wait)
                        continue
                    raise
            answers = [
                {
                    "answer": result.answer if hasattr(result, "answer") else str(result),
                    "score": round(float(getattr(result, "score", 0.0)), 4),
                    "start": getattr(result, "start", 0),
                    "end": getattr(result, "end", 0),
                }
            ]
            return answers
        except Exception as e:
            logger.error("extractive_qa_failed", error=str(e))
            return [{"answer": "Unable to generate an answer.", "score": 0.0}]

    def answer_from_chunks(
        self,
        question: str,
        chunks: List[Tuple[str, float]],
        top_k: int = 3,
    ) -> Dict:
        """
        Answer a question using multiple context chunks.

        Tries the generative (LLM) path first.  Falls back to extractive
        QA if the generative call fails.
        """
        # Build a single context string from the best chunks
        context_parts: list[str] = []
        total_chars = 0
        for chunk_text, _sim in chunks:
            if total_chars + len(chunk_text) > 6000:
                break
            context_parts.append(chunk_text)
            total_chars += len(chunk_text)

        combined_context = "\n\n".join(context_parts)

        # ------- 1. Try generative answer first ---------
        try:
            gen_result = self._generative_answer(question, combined_context)
            if gen_result:
                return gen_result
        except Exception as e:
            logger.warning("generative_qa_failed_falling_back", error=str(e))

        # ------- 2. Fallback: extractive QA -------------
        return self._extractive_answer_from_chunks(question, chunks, top_k)

    # --------------------------------------------------------------------- #
    # Generative (LLM) path
    # --------------------------------------------------------------------- #

    def _generative_answer(self, question: str, context: str) -> Optional[Dict]:
        """
        Use an instruct-tuned LLM to produce a detailed, structured,
        Markdown-formatted answer grounded in the retrieved context.
        """
        system_prompt = (
            "You are an expert AI research assistant that helps researchers "
            "understand academic papers. You provide detailed, well-structured, "
            "and insightful answers based on the provided paper context.\n\n"
            "Rules:\n"
            "- Answer ONLY based on the provided context. If the context does not "
            "contain enough information, say so clearly.\n"
            "- Use Markdown formatting: headings, bullet points, bold for key terms.\n"
            "- Provide a comprehensive, multi-paragraph answer when appropriate.\n"
            "- Cite specific details, findings, methods, or data from the context.\n"
            "- If the question asks for a summary, structure it with clear sections.\n"
            "- Be academic in tone but clear and accessible.\n"
        )

        user_prompt = (
            f"## Paper Context\n\n{context}\n\n"
            f"---\n\n"
            f"## Question\n\n{question}\n\n"
            f"Please provide a detailed, well-structured answer based on the paper context above."
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        max_retries = 3
        response = None
        for attempt in range(max_retries):
            try:
                response = self._client.chat_completion(
                    model=self._generative_model,
                    messages=messages,
                    max_tokens=1024,
                    temperature=0.3,
                    top_p=0.9,
                )
                break
            except Exception as retry_err:
                if "429" in str(retry_err) and attempt < max_retries - 1:
                    wait = 2 ** (attempt + 1)
                    logger.warning("hf_gen_rate_limited_retrying", attempt=attempt + 1, wait=wait)
                    time.sleep(wait)
                    continue
                raise

        answer_text = response.choices[0].message.content.strip()

        if not answer_text or len(answer_text) < 10:
            return None

        # Estimate confidence based on answer length & relevance signals
        confidence = min(0.95, 0.5 + len(answer_text) / 2000)

        tokens_used = getattr(response, "usage", None)
        total_tokens = (
            tokens_used.total_tokens
            if tokens_used and hasattr(tokens_used, "total_tokens")
            else None
        )

        logger.info(
            "generative_answer_produced",
            question_len=len(question),
            answer_len=len(answer_text),
            tokens=total_tokens,
        )

        return {
            "answer": answer_text,
            "confidence": round(confidence, 4),
            "supporting_evidence": [],
            "tokens_used": total_tokens,
        }

    # --------------------------------------------------------------------- #
    # Extractive fallback
    # --------------------------------------------------------------------- #

    def _extractive_answer_from_chunks(
        self,
        question: str,
        chunks: List[Tuple[str, float]],
        top_k: int = 3,
    ) -> Dict:
        """Original extractive pipeline used as fallback."""
        all_answers = []

        for chunk_text, chunk_similarity in chunks:
            answers = self.answer(question, chunk_text, top_k=1)
            for ans in answers:
                combined_score = (ans["score"] * 0.6) + (chunk_similarity * 0.4)
                all_answers.append(
                    {
                        "answer": ans["answer"],
                        "qa_score": ans["score"],
                        "chunk_similarity": chunk_similarity,
                        "combined_score": combined_score,
                        "context": chunk_text,
                    }
                )

        all_answers.sort(key=lambda x: x["combined_score"], reverse=True)

        if not all_answers:
            return {
                "answer": "I couldn't find a relevant answer in the paper.",
                "confidence": 0.0,
                "supporting_evidence": [],
            }

        best = all_answers[0]
        supporting = all_answers[:top_k]

        answer_text = best["answer"]
        if len(answer_text.split()) < 5 and len(all_answers) > 1:
            unique_answers = []
            seen = set()
            for a in all_answers[:5]:
                normalized = a["answer"].lower().strip()
                if normalized not in seen and len(normalized) > 3:
                    seen.add(normalized)
                    unique_answers.append(a["answer"])
            answer_text = (
                ". ".join(unique_answers) if unique_answers else answer_text
            )

        return {
            "answer": answer_text,
            "confidence": round(best["combined_score"], 4),
            "supporting_evidence": [
                {
                    "text": s["answer"],
                    "score": round(s["combined_score"], 4),
                    "context_preview": s["context"][:200] + "...",
                }
                for s in supporting
            ],
        }


def get_qa_model() -> QAModel:
    return QAModel()
