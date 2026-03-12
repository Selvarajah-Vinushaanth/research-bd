# ============================================
# Utilities - Text Cleaning & Processing
# ============================================

from __future__ import annotations

import html
import re
import unicodedata
from typing import Dict, List, Optional

import structlog

logger = structlog.get_logger()


class TextCleaner:
    """
    Advanced text cleaning for research papers.
    Handles OCR artifacts, encoding issues, and format normalization.
    """

    # Common ligatures and their replacements
    LIGATURES = {
        "ﬁ": "fi",
        "ﬂ": "fl",
        "ﬀ": "ff",
        "ﬃ": "ffi",
        "ﬄ": "ffl",
        "ﬅ": "ft",
        "ﬆ": "st",
    }

    # Common OCR errors
    OCR_FIXES = {
        "rn": "m",  # Only applied contextually
        "l1": "ll",
        "0": "o",  # Only in word context
    }

    @staticmethod
    def clean_text(text: str) -> str:
        """
        Full text cleaning pipeline for research paper text.

        Args:
            text: Raw text extracted from PDF.

        Returns:
            Cleaned text suitable for NLP processing.
        """
        if not text:
            return ""

        # 1. Normalize unicode
        text = unicodedata.normalize("NFKC", text)

        # 2. Fix ligatures
        for lig, replacement in TextCleaner.LIGATURES.items():
            text = text.replace(lig, replacement)

        # 3. Decode HTML entities
        text = html.unescape(text)

        # 4. Fix hyphenated line breaks (common in PDFs)
        text = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", text)

        # 5. Fix line breaks within sentences
        text = re.sub(r"(?<=[a-z,;])\s*\n\s*(?=[a-z])", " ", text)

        # 6. Preserve paragraph breaks but clean up excessive newlines
        text = re.sub(r"\n{3,}", "\n\n", text)

        # 7. Remove page numbers (standalone numbers on lines)
        text = re.sub(r"^\s*\d{1,4}\s*$", "", text, flags=re.MULTILINE)

        # 8. Clean whitespace
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r" +\n", "\n", text)

        # 9. Remove control characters (keep newlines and tabs)
        text = "".join(
            char for char in text
            if unicodedata.category(char)[0] != "C" or char in "\n\t\r"
        )

        # 10. Fix common encoding artifacts
        encoding_fixes = {
            "\u00e2\u0080\u0099": "'",
            "\u00e2\u0080\u009c": '"',
            "\u00e2\u0080\u009d": '"',
            "\u00e2\u0080\u0094": "\u2014",
            "\u00e2\u0080\u0093": "\u2013",
        }
        for bad, good in encoding_fixes.items():
            text = text.replace(bad, good)

        return text.strip()

    @staticmethod
    def extract_metadata_from_text(text: str) -> Dict[str, Optional[str]]:
        """
        Extract metadata fields from paper text heuristically.
        """
        metadata = {
            "title": None,
            "abstract": None,
            "authors": None,
            "doi": None,
            "keywords": None,
        }

        lines = text.split("\n")

        # Extract title (usually first non-empty lines, before authors)
        title_lines = []
        for line in lines[:10]:
            line = line.strip()
            if line and len(line) > 5 and not re.match(r"^\d", line):
                title_lines.append(line)
                if len(" ".join(title_lines)) > 20:
                    break
        if title_lines:
            metadata["title"] = " ".join(title_lines)

        # Extract abstract
        abstract_match = re.search(
            r"(?:abstract|summary)\s*[:\.]?\s*\n?(.*?)(?:\n\s*(?:\d+\.?\s*)?(?:introduction|keywords|1\.|I\.))",
            text,
            re.IGNORECASE | re.DOTALL,
        )
        if abstract_match:
            abstract = abstract_match.group(1).strip()
            abstract = re.sub(r"\s+", " ", abstract)
            if len(abstract) > 50:
                metadata["abstract"] = abstract

        # Extract DOI
        doi_match = re.search(r"(?:doi|DOI)\s*:?\s*(10\.\d{4,}/\S+)", text)
        if doi_match:
            metadata["doi"] = doi_match.group(1).rstrip(".")

        # Extract keywords
        kw_match = re.search(
            r"(?:keywords?|key\s*words?|index\s*terms?)\s*[:\.]?\s*\n?(.*?)(?:\n\s*(?:\d+\.?\s*)?(?:introduction|1\.))",
            text,
            re.IGNORECASE | re.DOTALL,
        )
        if kw_match:
            keywords = kw_match.group(1).strip()
            keywords = re.sub(r"\s+", " ", keywords)
            metadata["keywords"] = keywords

        return metadata

    @staticmethod
    def extract_references(text: str) -> List[str]:
        """Extract reference entries from the references section."""
        # Find references section
        ref_match = re.search(
            r"(?:references|bibliography)\s*\n(.*)",
            text,
            re.IGNORECASE | re.DOTALL,
        )
        if not ref_match:
            return []

        ref_text = ref_match.group(1)

        # Split by reference numbers [1], [2], etc.
        refs = re.split(r"\n\s*\[?\d+\]?\s*\.?\s*", ref_text)

        # Clean and filter
        cleaned_refs = []
        for ref in refs:
            ref = re.sub(r"\s+", " ", ref).strip()
            if len(ref) > 20:  # Skip very short entries
                cleaned_refs.append(ref)

        return cleaned_refs

    @staticmethod
    def count_sections(text: str) -> Dict[str, int]:
        """Count detected sections, figures, tables, equations."""
        counts = {
            "figures": len(re.findall(r"(?:fig(?:ure)?\.?\s*\d+)", text, re.IGNORECASE)),
            "tables": len(re.findall(r"(?:table\s*\d+)", text, re.IGNORECASE)),
            "equations": len(re.findall(r"(?:\(\d+\)|\\\[|\\\(|\\begin\{equation\})", text)),
            "references": len(TextCleaner.extract_references(text)),
        }
        return counts

    @staticmethod
    def sanitize_input(text: str) -> str:
        """Sanitize user input for security."""
        if not text:
            return ""
        # Remove potential script injections
        text = re.sub(r"<script[^>]*>.*?</script>", "", text, flags=re.IGNORECASE | re.DOTALL)
        text = re.sub(r"<[^>]+>", "", text)
        text = html.escape(text)
        return text.strip()


def get_text_cleaner() -> TextCleaner:
    return TextCleaner()
