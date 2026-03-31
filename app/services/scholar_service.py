# ============================================
# Service - Google Scholar Integration
# ============================================
# Uses the `scholarly` library (free, no API key required)
# to search Google Scholar for academic papers and authors.
# ============================================

from __future__ import annotations

import asyncio
import concurrent.futures
from functools import lru_cache
from typing import Any, Dict, List, Optional

import structlog
from scholarly import scholarly

logger = structlog.get_logger()

# Timeout for scholarly blocking calls (seconds)
_SEARCH_TIMEOUT = 30


class ScholarService:
    """Service for interacting with Google Scholar via the scholarly library."""

    def __init__(self) -> None:
        self._initialized = False

    def _ensure_initialized(self) -> None:
        """Lazy initialization — scholarly doesn't need API keys."""
        if not self._initialized:
            self._initialized = True
            logger.info("scholar_service_initialized")

    async def search_papers(
        self,
        query: str,
        max_results: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Search Google Scholar for papers matching the query.
        Returns a list of paper metadata dicts.
        """
        self._ensure_initialized()

        def _do_search() -> List[Dict[str, Any]]:
            results: List[Dict[str, Any]] = []
            try:
                search_query = scholarly.search_pubs(query)
                for i, result in enumerate(search_query):
                    if i >= max_results:
                        break
                    results.append(self._parse_publication(result))
            except Exception as e:
                logger.error("scholar_search_failed", query=query, error=str(e))
                raise
            return results

        # Run blocking scholarly calls in thread pool with timeout
        loop = asyncio.get_event_loop()
        try:
            results = await asyncio.wait_for(
                loop.run_in_executor(None, _do_search),
                timeout=_SEARCH_TIMEOUT,
            )
        except asyncio.TimeoutError:
            logger.warning("scholar_search_timeout", query=query)
            results = []

        logger.info(
            "scholar_search_completed",
            query=query,
            result_count=len(results),
        )
        return results

    async def search_author(
        self,
        author_name: str,
    ) -> List[Dict[str, Any]]:
        """
        Search for authors on Google Scholar.

        Google aggressively blocks the dedicated author-search endpoint with
        CAPTCHAs, so we fall back to searching papers with ``author:<name>``
        and aggregate unique authors from the results.
        """
        self._ensure_initialized()

        def _do_search() -> List[Dict[str, Any]]:
            # Use paper search with author: prefix – this endpoint is less
            # aggressively rate-limited than the author profiles page.
            author_map: Dict[str, Dict[str, Any]] = {}
            try:
                search_query = scholarly.search_pubs(f"author:{author_name}")
                for i, pub in enumerate(search_query):
                    if i >= 20:  # scan more papers to find unique authors
                        break
                    bib = pub.get("bib", {}) if isinstance(pub, dict) else getattr(pub, "bib", {})
                    authors_raw = bib.get("author", "") if isinstance(bib, dict) else getattr(bib, "author", "")
                    if isinstance(authors_raw, str):
                        authors = [a.strip() for a in authors_raw.split(" and ")] if authors_raw else []
                    elif isinstance(authors_raw, list):
                        authors = authors_raw
                    else:
                        authors = []

                    venue = (bib.get("venue") or bib.get("journal") or "") if isinstance(bib, dict) else ""
                    num_citations = 0
                    info = pub if isinstance(pub, dict) else {}
                    try:
                        num_citations = int(info.get("num_citations", 0) or 0)
                    except (ValueError, TypeError):
                        pass

                    for author in authors:
                        key = author.lower().strip()
                        if not key:
                            continue
                        if key not in author_map:
                            author_map[key] = {
                                "name": author,
                                "affiliation": venue if venue else None,
                                "interests": [],
                                "citation_count": num_citations,
                                "h_index": None,
                                "i10_index": None,
                                "scholar_id": None,
                                "url": None,
                                "thumbnail": None,
                                "_paper_count": 1,
                            }
                        else:
                            author_map[key]["citation_count"] += num_citations
                            author_map[key]["_paper_count"] += 1
                            if venue and not author_map[key]["affiliation"]:
                                author_map[key]["affiliation"] = venue
            except Exception as e:
                logger.error("scholar_author_search_failed", name=author_name, error=str(e))
                raise

            # Sort by total citation count and filter to those matching the query
            query_lower = author_name.lower()
            matched = [
                a for key, a in author_map.items()
                if query_lower in key
            ]
            # If no exact-ish match, return all
            if not matched:
                matched = list(author_map.values())

            matched.sort(key=lambda a: a["citation_count"], reverse=True)

            # Clean up internal key
            for a in matched:
                a.pop("_paper_count", None)

            return matched[:10]

        loop = asyncio.get_event_loop()
        try:
            results = await asyncio.wait_for(
                loop.run_in_executor(None, _do_search),
                timeout=_SEARCH_TIMEOUT,
            )
        except asyncio.TimeoutError:
            logger.warning("scholar_author_search_timeout", name=author_name)
            return []

        logger.info("scholar_author_search_completed", name=author_name, count=len(results))
        return results

    async def get_paper_details(
        self,
        scholar_id: str,
    ) -> Optional[Dict[str, Any]]:
        """Fetch detailed info for a specific paper by scholar_id (title lookup)."""
        self._ensure_initialized()

        def _do_fetch() -> Optional[Dict[str, Any]]:
            try:
                search_query = scholarly.search_pubs(scholar_id)
                result = next(search_query, None)
                if result:
                    filled = scholarly.fill(result)
                    return self._parse_publication(filled)
            except Exception as e:
                logger.error("scholar_detail_fetch_failed", scholar_id=scholar_id, error=str(e))
            return None

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _do_fetch)

    @staticmethod
    def _parse_publication(pub: Any) -> Dict[str, Any]:
        """Extract structured data from a scholarly publication object."""
        bib = getattr(pub, "bib", {}) if hasattr(pub, "bib") else pub.get("bib", {})
        info = pub if isinstance(pub, dict) else pub.__dict__ if hasattr(pub, "__dict__") else {}

        # Handle both dict-style and attribute-style access
        def _get(obj: Any, key: str, default: Any = None) -> Any:
            if isinstance(obj, dict):
                return obj.get(key, default)
            return getattr(obj, key, default)

        authors_raw = _get(bib, "author", "")
        if isinstance(authors_raw, str):
            authors = [a.strip() for a in authors_raw.split(" and ")] if authors_raw else []
        elif isinstance(authors_raw, list):
            authors = authors_raw
        else:
            authors = []

        pub_year = _get(bib, "pub_year") or _get(bib, "year")
        try:
            pub_year = int(pub_year) if pub_year else None
        except (ValueError, TypeError):
            pub_year = None

        num_citations = _get(info, "num_citations", 0)
        try:
            num_citations = int(num_citations) if num_citations else 0
        except (ValueError, TypeError):
            num_citations = 0

        return {
            "scholar_id": _get(info, "author_pub_id") or _get(info, "cites_id", [None])[0] if isinstance(_get(info, "cites_id"), list) else _get(info, "cites_id"),
            "title": _get(bib, "title", "Untitled"),
            "authors": authors,
            "abstract": _get(bib, "abstract"),
            "publication_year": pub_year,
            "journal": _get(bib, "venue") or _get(bib, "journal") or _get(bib, "publisher"),
            "citation_count": num_citations,
            "url": _get(info, "pub_url") or _get(info, "eprint_url"),
            "pdf_url": _get(info, "eprint_url"),
            "doi": None,  # scholarly doesn't reliably return DOI
        }

    @staticmethod
    def _parse_author(author: Any) -> Dict[str, Any]:
        """Extract structured data from a scholarly author object."""
        # scholarly returns dicts with known keys
        info = author if isinstance(author, dict) else vars(author) if hasattr(author, "__dict__") else {}

        def _get(obj: Any, key: str, default: Any = None) -> Any:
            if isinstance(obj, dict):
                return obj.get(key, default)
            return getattr(obj, key, default)

        # citation count: scholarly uses both "citedby" and "cited_by" depending on version
        cited = _get(info, "citedby") or _get(info, "cited_by") or _get(info, "citedby5y") or 0
        try:
            cited = int(cited)
        except (ValueError, TypeError):
            cited = 0

        h_index = _get(info, "hindex") or _get(info, "hindex5y")
        try:
            h_index = int(h_index) if h_index is not None else None
        except (ValueError, TypeError):
            h_index = None

        i10 = _get(info, "i10index") or _get(info, "i10index5y")
        try:
            i10 = int(i10) if i10 is not None else None
        except (ValueError, TypeError):
            i10 = None

        scholar_id = _get(info, "scholar_id")

        return {
            "name": _get(info, "name", "Unknown"),
            "affiliation": _get(info, "affiliation") or _get(info, "email_domain"),
            "interests": _get(info, "interests", []) or [],
            "citation_count": cited,
            "h_index": h_index,
            "i10_index": i10,
            "scholar_id": scholar_id,
            "url": f"https://scholar.google.com/citations?user={scholar_id}" if scholar_id else None,
            "thumbnail": _get(info, "url_picture"),
        }


# --- Singleton ---
_scholar_service: Optional[ScholarService] = None


def get_scholar_service() -> ScholarService:
    """Return a singleton ScholarService instance."""
    global _scholar_service
    if _scholar_service is None:
        _scholar_service = ScholarService()
    return _scholar_service
