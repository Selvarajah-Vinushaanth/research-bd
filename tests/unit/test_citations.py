"""
Unit tests for citation service.
"""

import pytest


class TestCitationService:

    @pytest.fixture(autouse=True)
    def _setup(self):
        from app.services.citation_service import CitationService
        self.service = CitationService()

    def test_generate_apa(self):
        paper = {
            "title": "Attention Is All You Need",
            "authors": ["Vaswani, A.", "Shazeer, N."],
            "publishedYear": 2017,
            "journal": "NeurIPS",
        }
        citation = self.service.generate_citation(paper, "APA")
        assert "Attention Is All You Need" in citation
        assert "2017" in citation

    def test_generate_mla(self):
        paper = {
            "title": "Deep Learning",
            "authors": ["LeCun, Y.", "Bengio, Y.", "Hinton, G."],
            "publishedYear": 2015,
            "journal": "Nature",
        }
        citation = self.service.generate_citation(paper, "MLA")
        assert "Deep Learning" in citation

    def test_generate_ieee(self):
        paper = {
            "title": "BERT: Pre-training",
            "authors": ["Devlin, J."],
            "publishedYear": 2019,
            "journal": "ACL",
        }
        citation = self.service.generate_citation(paper, "IEEE")
        assert "BERT" in citation

    def test_generate_bibtex(self):
        paper = {
            "title": "GPT-3 Language Models",
            "authors": ["Brown, T."],
            "publishedYear": 2020,
            "journal": "NeurIPS",
        }
        citation = self.service.generate_citation(paper, "BIBTEX")
        assert "@article" in citation or "@inproceedings" in citation.lower() or "title" in citation.lower()

    def test_generate_chicago(self):
        paper = {
            "title": "ResNet",
            "authors": ["He, K.", "Zhang, X."],
            "publishedYear": 2016,
            "journal": "CVPR",
        }
        citation = self.service.generate_citation(paper, "CHICAGO")
        assert "ResNet" in citation

    def test_generate_harvard(self):
        paper = {
            "title": "AlexNet",
            "authors": ["Krizhevsky, A."],
            "publishedYear": 2012,
            "journal": "NeurIPS",
        }
        citation = self.service.generate_citation(paper, "HARVARD")
        assert "AlexNet" in citation

    def test_no_authors(self):
        paper = {
            "title": "Anonymous Paper",
            "authors": [],
            "publishedYear": 2023,
        }
        citation = self.service.generate_citation(paper, "APA")
        # Should still produce something meaningful
        assert "Anonymous Paper" in citation

    def test_missing_year(self):
        paper = {
            "title": "Timeless Paper",
            "authors": ["Author, A."],
        }
        citation = self.service.generate_citation(paper, "APA")
        assert "Timeless Paper" in citation
