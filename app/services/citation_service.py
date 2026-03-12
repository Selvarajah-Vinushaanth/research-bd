# ============================================
# Service - Citation Generation
# ============================================

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

import structlog

from app.database.prisma_client import get_db

logger = structlog.get_logger()


class CitationService:
    """
    Generate citations in multiple academic formats.
    Supports APA 7th, MLA 9th, IEEE, Chicago, Harvard, and BibTeX.
    """

    def __init__(self):
        self.db = get_db()

    async def generate_citation(
        self,
        paper_id: str,
        format: str = "APA",
    ) -> Dict[str, str]:
        """
        Generate a citation for a paper in the specified format.

        Args:
            paper_id: The paper ID.
            format: Citation format (APA, MLA, IEEE, CHICAGO, HARVARD, BIBTEX).

        Returns:
            Dict with 'format' and 'citation_text'.
        """
        format_upper = format.upper()

        # Check for cached citation first
        existing = await self.db.citation.find_first(
            where={"paper_id": paper_id, "format": format_upper}
        )
        if existing:
            return {
                "paper_id": paper_id,
                "format": format_upper,
                "citation_text": existing.citation_text,
            }

        # Get paper data
        paper = await self.db.paper.find_unique(where={"id": paper_id})
        if not paper:
            raise ValueError(f"Paper not found: {paper_id}")

        authors = paper.authors or []
        title = paper.title or "Untitled"
        year = paper.publication_date.year if paper.publication_date else datetime.now().year
        journal = paper.journal or ""
        doi = paper.doi or ""

        format_upper = format.upper()
        generators = {
            "APA": self._format_apa,
            "MLA": self._format_mla,
            "IEEE": self._format_ieee,
            "CHICAGO": self._format_chicago,
            "HARVARD": self._format_harvard,
            "BIBTEX": self._format_bibtex,
        }

        generator = generators.get(format_upper)
        if not generator:
            raise ValueError(f"Unsupported citation format: {format}")

        citation_text = generator(
            authors=authors,
            title=title,
            year=year,
            journal=journal,
            doi=doi,
        )

        # Cache the citation
        await self.db.citation.create(
            data={
                "paper_id": paper_id,
                "citation_text": citation_text,
                "format": format_upper,
            }
        )

        return {
            "paper_id": paper_id,
            "format": format_upper,
            "citation_text": citation_text,
        }

    async def generate_all_formats(self, paper_id: str) -> List[Dict[str, str]]:
        """Generate citations in all supported formats."""
        formats = ["APA", "MLA", "IEEE", "CHICAGO", "HARVARD", "BIBTEX"]
        citations = []
        for fmt in formats:
            try:
                citation = await self.generate_citation(paper_id, fmt)
                citations.append(citation)
            except Exception as e:
                logger.warning("citation_generation_failed", format=fmt, error=str(e))
        return citations

    # --- Format Generators ---

    def _format_apa(
        self, authors: List[str], title: str, year: int, journal: str, doi: str
    ) -> str:
        """APA 7th Edition format."""
        # Format authors: Last, F. M., Last, F. M., & Last, F. M.
        formatted_authors = self._format_authors_apa(authors)
        citation = f"{formatted_authors} ({year}). {title}."
        if journal:
            citation += f" *{journal}*."
        if doi:
            citation += f" https://doi.org/{doi}"
        return citation

    def _format_mla(
        self, authors: List[str], title: str, year: int, journal: str, doi: str
    ) -> str:
        """MLA 9th Edition format."""
        formatted_authors = self._format_authors_mla(authors)
        citation = f'{formatted_authors} "{title}."'
        if journal:
            citation += f" *{journal}*,"
        citation += f" {year}."
        if doi:
            citation += f" doi:{doi}."
        return citation

    def _format_ieee(
        self, authors: List[str], title: str, year: int, journal: str, doi: str
    ) -> str:
        """IEEE format."""
        formatted_authors = self._format_authors_ieee(authors)
        citation = f'{formatted_authors}, "{title},"'
        if journal:
            citation += f" *{journal}*,"
        citation += f" {year}."
        if doi:
            citation += f" doi: {doi}."
        return citation

    def _format_chicago(
        self, authors: List[str], title: str, year: int, journal: str, doi: str
    ) -> str:
        """Chicago Manual of Style format."""
        formatted_authors = self._format_authors_chicago(authors)
        citation = f'{formatted_authors}. "{title}."'
        if journal:
            citation += f" *{journal}*"
        citation += f" ({year})."
        if doi:
            citation += f" https://doi.org/{doi}."
        return citation

    def _format_harvard(
        self, authors: List[str], title: str, year: int, journal: str, doi: str
    ) -> str:
        """Harvard format."""
        formatted_authors = self._format_authors_harvard(authors)
        citation = f"{formatted_authors} ({year}) '{title}',"
        if journal:
            citation += f" *{journal}*."
        else:
            citation += "."
        if doi:
            citation += f" Available at: https://doi.org/{doi}."
        return citation

    def _format_bibtex(
        self, authors: List[str], title: str, year: int, journal: str, doi: str
    ) -> str:
        """BibTeX format."""
        # Generate a cite key
        first_author_last = authors[0].split()[-1].lower() if authors else "unknown"
        cite_key = f"{first_author_last}{year}"
        author_str = " and ".join(authors) if authors else "Unknown"

        bibtex = f"@article{{{cite_key},\n"
        bibtex += f"  author = {{{author_str}}},\n"
        bibtex += f"  title = {{{title}}},\n"
        bibtex += f"  year = {{{year}}},\n"
        if journal:
            bibtex += f"  journal = {{{journal}}},\n"
        if doi:
            bibtex += f"  doi = {{{doi}}},\n"
        bibtex += "}"
        return bibtex

    # --- Author Formatting Helpers ---

    def _format_authors_apa(self, authors: List[str]) -> str:
        if not authors:
            return "Unknown Author"
        if len(authors) == 1:
            return self._last_initials(authors[0])
        if len(authors) == 2:
            return f"{self._last_initials(authors[0])}, & {self._last_initials(authors[1])}"
        if len(authors) <= 20:
            parts = [self._last_initials(a) for a in authors[:-1]]
            return ", ".join(parts) + f", & {self._last_initials(authors[-1])}"
        # 21+ authors: first 19, ..., last
        parts = [self._last_initials(a) for a in authors[:19]]
        return ", ".join(parts) + f", ... {self._last_initials(authors[-1])}"

    def _format_authors_mla(self, authors: List[str]) -> str:
        if not authors:
            return "Unknown Author"
        if len(authors) == 1:
            return self._last_first(authors[0])
        if len(authors) == 2:
            return f"{self._last_first(authors[0])}, and {authors[1]}"
        return f"{self._last_first(authors[0])}, et al"

    def _format_authors_ieee(self, authors: List[str]) -> str:
        if not authors:
            return "Unknown Author"
        formatted = [self._initials_last(a) for a in authors[:6]]
        if len(authors) > 6:
            formatted.append("et al.")
        return ", ".join(formatted)

    def _format_authors_chicago(self, authors: List[str]) -> str:
        if not authors:
            return "Unknown Author"
        if len(authors) == 1:
            return self._last_first(authors[0])
        return f"{self._last_first(authors[0])}, et al"

    def _format_authors_harvard(self, authors: List[str]) -> str:
        if not authors:
            return "Unknown Author"
        if len(authors) <= 3:
            formatted = [self._last_initials(a) for a in authors]
            return ", ".join(formatted[:-1]) + " and " + formatted[-1] if len(formatted) > 1 else formatted[0]
        return f"{self._last_initials(authors[0])} et al."

    # --- Name Formatting Helpers ---

    def _last_initials(self, name: str) -> str:
        """Convert 'John Doe Smith' to 'Smith, J. D.'"""
        parts = name.strip().split()
        if len(parts) == 1:
            return parts[0]
        last = parts[-1]
        initials = " ".join(f"{p[0]}." for p in parts[:-1])
        return f"{last}, {initials}"

    def _last_first(self, name: str) -> str:
        """Convert 'John Smith' to 'Smith, John'."""
        parts = name.strip().split()
        if len(parts) == 1:
            return parts[0]
        return f"{parts[-1]}, {' '.join(parts[:-1])}"

    def _initials_last(self, name: str) -> str:
        """Convert 'John Doe Smith' to 'J. D. Smith'."""
        parts = name.strip().split()
        if len(parts) == 1:
            return parts[0]
        initials = " ".join(f"{p[0]}." for p in parts[:-1])
        return f"{initials} {parts[-1]}"


def get_citation_service() -> CitationService:
    return CitationService()
