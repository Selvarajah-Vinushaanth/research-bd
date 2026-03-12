# ============================================
# Utilities - Text Chunking
# ============================================

from __future__ import annotations

import re
from typing import List, Optional, Tuple

import structlog

from app.config import settings

logger = structlog.get_logger()


class TextChunker:
    """
    Advanced text chunking for research papers.
    Supports token-based and semantic chunking with overlap.
    """

    def __init__(
        self,
        chunk_size: int = settings.CHUNK_SIZE,
        chunk_overlap: int = settings.CHUNK_OVERLAP,
    ):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def chunk_by_tokens(self, text: str) -> List[dict]:
        """
        Split text into chunks based on approximate token count.
        Each chunk includes metadata about position and section.

        Returns:
            List of dicts with 'text', 'index', 'token_count', 'section'.
        """
        if not text or not text.strip():
            return []

        # Clean the text first
        text = self._clean_for_chunking(text)

        # Try to detect sections
        sections = self._detect_sections(text)

        if sections:
            return self._chunk_by_sections(sections)

        # Fall back to sliding window chunking
        return self._sliding_window_chunk(text)

    def _sliding_window_chunk(self, text: str, section: Optional[str] = None) -> List[dict]:
        """Sliding window chunking with overlap."""
        words = text.split()
        chunks = []
        index = 0

        i = 0
        while i < len(words):
            end = min(i + self.chunk_size, len(words))
            chunk_words = words[i:end]
            chunk_text = " ".join(chunk_words)

            if len(chunk_text.strip()) > 20:  # Skip very short chunks
                chunks.append({
                    "text": chunk_text.strip(),
                    "index": index,
                    "token_count": len(chunk_words),
                    "section": section,
                })
                index += 1

            # Move forward by (chunk_size - overlap)
            step = max(1, self.chunk_size - self.chunk_overlap)
            i += step

        logger.debug("text_chunked", total_words=len(words), chunks=len(chunks))
        return chunks

    def _detect_sections(self, text: str) -> List[Tuple[str, str]]:
        """
        Detect common research paper sections.
        Returns list of (section_name, section_text) tuples.
        """
        section_patterns = [
            r"(?:^|\n)\s*(abstract)\s*[:\.]?\s*\n",
            r"(?:^|\n)\s*(\d+\.?\s*introduction)\s*[:\.]?\s*\n",
            r"(?:^|\n)\s*(\d+\.?\s*(?:related\s+work|literature\s+review|background))\s*[:\.]?\s*\n",
            r"(?:^|\n)\s*(\d+\.?\s*(?:method(?:ology|s)?|approach|framework))\s*[:\.]?\s*\n",
            r"(?:^|\n)\s*(\d+\.?\s*(?:experiment(?:s|al)?(?:\s+(?:setup|results))?|evaluation))\s*[:\.]?\s*\n",
            r"(?:^|\n)\s*(\d+\.?\s*(?:results?(?:\s+and\s+discussion)?|findings))\s*[:\.]?\s*\n",
            r"(?:^|\n)\s*(\d+\.?\s*discussion)\s*[:\.]?\s*\n",
            r"(?:^|\n)\s*(\d+\.?\s*(?:conclusion(?:s)?|summary))\s*[:\.]?\s*\n",
            r"(?:^|\n)\s*(?:references|bibliography)\s*[:\.]?\s*\n",
        ]

        # Find all section positions
        positions = []
        for pattern in section_patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                section_name = match.group(1) if match.lastindex else match.group(0)
                section_name = re.sub(r"^\d+\.?\s*", "", section_name).strip().lower()
                positions.append((match.start(), match.end(), section_name))

        if len(positions) < 2:
            return []

        positions.sort(key=lambda x: x[0])

        # Extract section text
        sections = []
        for i, (start, end, name) in enumerate(positions):
            next_start = positions[i + 1][0] if i + 1 < len(positions) else len(text)
            section_text = text[end:next_start].strip()
            if section_text:
                sections.append((name, section_text))

        return sections

    def _chunk_by_sections(self, sections: List[Tuple[str, str]]) -> List[dict]:
        """Chunk text respecting section boundaries."""
        all_chunks = []
        global_index = 0

        for section_name, section_text in sections:
            section_chunks = self._sliding_window_chunk(section_text, section=section_name)
            for chunk in section_chunks:
                chunk["index"] = global_index
                global_index += 1
                all_chunks.append(chunk)

        return all_chunks

    def _clean_for_chunking(self, text: str) -> str:
        """Clean text specifically for chunking."""
        # Remove excessive whitespace but preserve paragraph breaks
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r" {2,}", " ", text)
        # Remove page numbers
        text = re.sub(r"\n\s*\d+\s*\n", "\n", text)
        # Remove headers/footers (common patterns)
        text = re.sub(r"\n.*(?:page|pg\.?)\s*\d+.*\n", "\n", text, flags=re.IGNORECASE)
        return text.strip()

    def merge_small_chunks(self, chunks: List[dict], min_tokens: int = 50) -> List[dict]:
        """Merge chunks that are too small with adjacent chunks."""
        if not chunks:
            return chunks

        merged = []
        buffer = None

        for chunk in chunks:
            if buffer is None:
                buffer = chunk.copy()
            elif buffer["token_count"] < min_tokens:
                buffer["text"] += " " + chunk["text"]
                buffer["token_count"] += chunk["token_count"]
            else:
                merged.append(buffer)
                buffer = chunk.copy()

        if buffer:
            merged.append(buffer)

        # Re-index
        for i, chunk in enumerate(merged):
            chunk["index"] = i

        return merged


def get_chunker() -> TextChunker:
    return TextChunker()
