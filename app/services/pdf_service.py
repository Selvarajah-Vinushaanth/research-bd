# ============================================
# Service - PDF Processing
# ============================================

from __future__ import annotations

import hashlib
import io
import time
from typing import Dict, List, Optional, Tuple

import fitz  # PyMuPDF
import structlog

from app.config import settings
from app.utils.text_cleaning import TextCleaner

logger = structlog.get_logger()


class PDFService:
    """
    Production-grade PDF processing service.
    Extracts text, metadata, and structural information from research papers.
    """

    MAX_PAGES = 500

    @staticmethod
    async def extract_text(file_content: bytes) -> Dict:
        """
        Extract text and metadata from a PDF file.

        Args:
            file_content: Raw PDF bytes.

        Returns:
            Dict with 'text', 'metadata', 'pages', 'page_texts'.
        """
        start_time = time.time()
        cleaner = TextCleaner()

        try:
            doc = fitz.open(stream=file_content, filetype="pdf")
        except Exception as e:
            logger.error("pdf_open_failed", error=str(e))
            raise ValueError(f"Failed to open PDF: {str(e)}")

        if doc.page_count > PDFService.MAX_PAGES:
            raise ValueError(f"PDF exceeds maximum page limit ({PDFService.MAX_PAGES} pages)")

        # Extract text from each page
        page_texts: List[str] = []
        full_text_parts: List[str] = []

        for page_num in range(doc.page_count):
            page = doc[page_num]
            text = page.get_text("text")
            cleaned = cleaner.clean_text(text)
            page_texts.append(cleaned)
            if cleaned:
                full_text_parts.append(cleaned)

        full_text = "\n\n".join(full_text_parts)

        # Extract metadata from PDF
        pdf_metadata = doc.metadata or {}
        title = pdf_metadata.get("title", "").strip()
        author = pdf_metadata.get("author", "").strip()
        subject = pdf_metadata.get("subject", "").strip()

        # Try to extract metadata from text if not in PDF metadata
        text_metadata = cleaner.extract_metadata_from_text(full_text)

        if not title and text_metadata.get("title"):
            title = text_metadata["title"]

        # Count elements
        element_counts = cleaner.count_sections(full_text)

        # Extract references
        references = cleaner.extract_references(full_text)

        # Compute file hash
        file_hash = hashlib.sha256(file_content).hexdigest()

        processing_time = time.time() - start_time

        result = {
            "text": full_text,
            "page_texts": page_texts,
            "page_count": doc.page_count,
            "file_hash": file_hash,
            "metadata": {
                "title": title or text_metadata.get("title", "Untitled"),
                "authors": [a.strip() for a in author.split(",")] if author else [],
                "abstract": text_metadata.get("abstract"),
                "doi": text_metadata.get("doi"),
                "keywords": (
                    [k.strip() for k in text_metadata["keywords"].split(",")]
                    if text_metadata.get("keywords")
                    else []
                ),
                "subject": subject,
            },
            "statistics": {
                "text_length": len(full_text),
                "figure_count": element_counts["figures"],
                "table_count": element_counts["tables"],
                "equation_count": element_counts["equations"],
                "reference_count": len(references),
            },
            "references": references,
            "processing_time": round(processing_time, 3),
        }

        doc.close()

        logger.info(
            "pdf_extracted",
            pages=result["page_count"],
            text_len=len(full_text),
            time=result["processing_time"],
        )

        return result

    @staticmethod
    async def extract_images(file_content: bytes) -> List[Dict]:
        """Extract images from a PDF for figure analysis."""
        doc = fitz.open(stream=file_content, filetype="pdf")
        images = []

        for page_num in range(doc.page_count):
            page = doc[page_num]
            image_list = page.get_images()

            for img_index, img in enumerate(image_list):
                xref = img[0]
                try:
                    base_image = doc.extract_image(xref)
                    images.append({
                        "page": page_num + 1,
                        "index": img_index,
                        "width": base_image.get("width", 0),
                        "height": base_image.get("height", 0),
                        "format": base_image.get("ext", "unknown"),
                        "size": len(base_image.get("image", b"")),
                    })
                except Exception:
                    continue

        doc.close()
        return images

    @staticmethod
    def validate_pdf(file_content: bytes) -> Tuple[bool, str]:
        """
        Validate a PDF file for processing.

        Returns:
            Tuple of (is_valid, message).
        """
        if not file_content:
            return False, "Empty file"

        if len(file_content) > settings.max_upload_bytes:
            return False, f"File exceeds {settings.MAX_UPLOAD_SIZE_MB}MB limit"

        # Check PDF magic bytes
        if not file_content[:5] == b"%PDF-":
            return False, "Not a valid PDF file"

        try:
            doc = fitz.open(stream=file_content, filetype="pdf")
            if doc.page_count == 0:
                doc.close()
                return False, "PDF has no pages"
            if doc.page_count > PDFService.MAX_PAGES:
                doc.close()
                return False, f"PDF exceeds {PDFService.MAX_PAGES} page limit"
            doc.close()
        except Exception as e:
            return False, f"Invalid PDF: {str(e)}"

        return True, "Valid PDF"

    @staticmethod
    def compute_hash(file_content: bytes) -> str:
        """Compute SHA-256 hash of file content."""
        return hashlib.sha256(file_content).hexdigest()


def get_pdf_service() -> PDFService:
    return PDFService()
