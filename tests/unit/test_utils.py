"""
Unit tests for text utilities.
"""

import pytest

from app.utils.text_cleaning import TextCleaner
from app.utils.chunking import TextChunker


# =====================================================================
# TextCleaner tests
# =====================================================================

class TestTextCleaner:

    def test_clean_basic_text(self):
        raw = "  Hello   World  \n\n\n  Test  "
        result = TextCleaner.clean_text(raw)
        assert "Hello" in result
        assert "World" in result

    def test_clean_removes_excessive_newlines(self):
        raw = "Line 1\n\n\n\n\n\nLine 2"
        result = TextCleaner.clean_text(raw)
        # Should collapse to at most 2 consecutive newlines
        assert "\n\n\n" not in result

    def test_clean_empty_string(self):
        assert TextCleaner.clean_text("") == ""
        assert TextCleaner.clean_text("   ") == ""

    def test_extract_metadata_with_doi(self):
        text = "Some paper content. DOI: 10.1234/test.5678 more text."
        meta = TextCleaner.extract_metadata(text)
        assert meta.get("doi") is not None

    def test_extract_metadata_no_doi(self):
        text = "Just some random text without any identifiers."
        meta = TextCleaner.extract_metadata(text)
        assert meta.get("doi") is None or meta["doi"] == ""

    def test_sanitize_input_strips_html(self):
        raw = "<script>alert('xss')</script>Hello"
        result = TextCleaner.sanitize_input(raw)
        assert "<script>" not in result

    def test_sanitize_input_length_limit(self):
        raw = "a" * 20000
        result = TextCleaner.sanitize_input(raw, max_length=100)
        assert len(result) <= 100

    def test_count_sections(self):
        text = (
            "1. Introduction\n"
            "Some content.\n"
            "2. Methods\n"
            "More content.\n"
            "3. Results\n"
            "Final content.\n"
        )
        count = TextCleaner.count_sections(text)
        assert count >= 2  # Should detect numbered sections


# =====================================================================
# TextChunker tests
# =====================================================================

class TestTextChunker:

    def test_chunk_text_basic(self):
        text = "Word " * 500  # ~500 words
        chunks = TextChunker.chunk_text(text, chunk_size=100, overlap=20)
        assert len(chunks) > 1
        for chunk in chunks:
            assert len(chunk.strip()) > 0

    def test_chunk_text_short(self):
        text = "This is a very short text."
        chunks = TextChunker.chunk_text(text, chunk_size=100, overlap=20)
        assert len(chunks) == 1
        assert chunks[0].strip() == text

    def test_chunk_text_empty(self):
        chunks = TextChunker.chunk_text("", chunk_size=100, overlap=20)
        assert len(chunks) == 0

    def test_chunk_text_overlap(self):
        words = [f"word{i}" for i in range(200)]
        text = " ".join(words)
        chunks = TextChunker.chunk_text(text, chunk_size=50, overlap=10)
        # Adjacent chunks should share some content (overlap)
        if len(chunks) >= 2:
            first_words = set(chunks[0].split())
            second_words = set(chunks[1].split())
            overlap = first_words & second_words
            assert len(overlap) > 0

    def test_section_aware_chunking(self):
        text = (
            "Introduction\n"
            "This is the intro section with enough content to fill a chunk. " * 10 + "\n"
            "Methods\n"
            "This is the methods section with detailed methodology. " * 10 + "\n"
            "Results\n"
            "Here are the results of our study with analysis. " * 10 + "\n"
        )
        chunks = TextChunker.section_aware_chunk(text, chunk_size=50, overlap=10)
        assert len(chunks) >= 1

    def test_chunk_preserves_content(self):
        text = "Alpha Bravo Charlie Delta Echo Foxtrot Golf Hotel India Juliet"
        chunks = TextChunker.chunk_text(text, chunk_size=5, overlap=1)
        # Reassemble (ignoring overlap) — all original words should appear
        all_words = set()
        for chunk in chunks:
            all_words.update(chunk.split())
        for word in text.split():
            assert word in all_words
