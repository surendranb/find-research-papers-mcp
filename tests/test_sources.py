# SPDX-License-Identifier: Apache-2.0

"""Adapter unit tests: pure-function parsing + mocked-HTTP search flows."""

import json

import pytest

from papers_mcp.sources import SOURCES, guess_id_type, search_all
from papers_mcp.sources.arxiv import ArxivSource, _norm_text
from papers_mcp.sources.base import PaperHit
from papers_mcp.sources.crossref import CrossrefSource, _strip_abstract
from papers_mcp.sources.openalex import OpenAlexSource, _reconstruct_abstract
from papers_mcp.sources.pubmed import PubMedSource
from papers_mcp.sources.semanticscholar import SemanticScholarSource

# ---------------------------------------------------------------------------
# Pure functions
# ---------------------------------------------------------------------------

class TestReconstructAbstract:
    def test_reconstructs_in_order(self):
        idx = {"attention": [0], "is": [1], "all": [2], "you": [3], "need": [4]}
        assert _reconstruct_abstract(idx) == "attention is all you need"

    def test_handles_gaps_and_none(self):
        assert _reconstruct_abstract(None) == ""
        assert _reconstruct_abstract({}) == ""
        # missing position 1 collapses into the join (single space between
        # surviving words), matching OpenAlex's canonical reconstruction
        assert _reconstruct_abstract({"the": [0], "end": [2]}) == "the end"


class TestStripAbstract:
    def test_strips_jats_tags(self):
        raw = "<jats:p>We show <jats:italic>transformers</jats:italic> work.</jats:p>"
        out = _strip_abstract(raw)
        assert "transformers" in out and "<" not in out

    def test_empty(self):
        assert _strip_abstract("") == ""
        assert _strip_abstract(None) == ""


class TestGuessIdType:
    @pytest.mark.parametrize("identifier,expected", [
        ("10.1038/s41586-020-2649-2", "doi"),
        ("https://doi.org/10.1038/s41586-020-2649-2", "doi"),
        ("doi:10.1038/nature14539", "doi"),
        ("1706.03762", "arxiv"),
        ("1706.03762v2", "arxiv"),
        ("hep-th/9901001", "arxiv"),
        ("https://arxiv.org/abs/1706.03762", "arxiv"),
        ("https://arxiv.org/pdf/1706.03762v3", "arxiv"),
        ("32513646", "pmid"),
        ("pmid:32513646", "pmid"),
        ("https://pubmed.ncbi.nlm.nih.gov/32513646/", "pmid"),
        ("W2741809807", "openalex"),
        ("openalex:W2741809807", "openalex"),
        ("https://openalex.org/works/W2741809807", "openalex"),
        ("649def34-4858-4af4-8a2c-6d3f7d4b9b3a", "s2"),
        ("s2:649def34-4858-4af4-8a2c-6d3f7d4b9b3a", "s2"),
    ])
    def test_guesses(self, identifier, expected):
        assert guess_id_type(identifier) == expected


class TestArxivParsing:
    def test_norm_text_collapses_whitespace(self):
        assert _norm_text("  Attention\n   Is All   ") == "Attention Is All"

    def test_parse_entry_from_fixture_xml(self):
        import xml.etree.ElementTree as ET
        xml = """<?xml version="1.0"?>
        <feed xmlns="http://www.w3.org/2005/Atom"
              xmlns:arxiv="http://arxiv.org/schemas/atom">
          <entry>
            <id>http://arxiv.org/abs/1706.03762v1</id>
            <published>2017-06-12T17:42:36Z</published>
            <title>Attention Is All You Need</title>
            <summary>The dominant sequence transduction models are based on complex recurrent or convolutional neural networks.</summary>
            <author><name>Ashish Vaswani</name></author>
            <author><name>Noam Shazeer</name></author>
            <arxiv:category term="cs.CL"/>
            <arxiv:doi>10.48550/arXiv.1706.03762</arxiv:doi>
          </entry>
        </feed>"""
        root = ET.fromstring(xml)
        entry = root.find("{http://www.w3.org/2005/Atom}entry")
        assert entry is not None
        hit = ArxivSource()._parse_entry(entry)
        assert hit.id == "1706.03762v1"
        assert hit.title == "Attention Is All You Need"
        assert hit.authors == ["Ashish Vaswani", "Noam Shazeer"]
        assert hit.year == 2017
        assert hit.doi == "10.48550/arXiv.1706.03762"
        assert hit.url == "https://arxiv.org/abs/1706.03762v1"
        assert hit.pdf_url == "https://arxiv.org/pdf/1706.03762v1"
        assert hit.open_access is True
        assert hit.type == "preprint"
        assert "cs.CL" in hit.extra["categories"]


class TestCrossrefParsing:
    def test_parse_item(self):
        src = CrossrefSource()
        item = {
            "DOI": "10.1038/s41586-020-2649-2",
            "title": ["Highly accurate protein structure prediction with AlphaFold"],
            "author": [{"given": "John", "family": "Jumper"}, {"given": "Jane", "family": "Doe"}],
            "issued": {"date-parts": [[2021, 7, 15]]},
            "container-title": ["Nature"],
            "abstract": "<jats:p>Proteins are essential to life.</jats:p>",
            "URL": "https://www.nature.com/articles/s41586-020-2649-2",
            "publisher": "Springer Science and Business Media LLC",
            "is-referenced-by-count": 10000,
            "type": "journal-article",
            "link": [{"URL": "https://www.nature.com/articles/s41586-020-2649-2.pdf",
                      "content-type": "application/pdf"}],
        }
        hit = src._parse_item(item)
        assert hit.id == "10.1038/s41586-020-2649-2"
        assert hit.title.startswith("Highly accurate")
        assert hit.authors == ["John Jumper", "Jane Doe"]
        assert hit.year == 2021
        assert hit.venue == "Nature"
        assert "Proteins" in hit.abstract
        assert hit.citations_count == 10000
        assert hit.pdf_url is not None and hit.pdf_url.endswith(".pdf")

    def test_get_rejects_non_doi(self):
        assert CrossrefSource().get("not-a-doi") is None


class TestOpenAlexParsing:
    def test_parse_work(self):
        src = OpenAlexSource()
        work = {
            "id": "https://openalex.org/W2741809807",
            "display_name": "Attention Is All You Need",
            "publication_year": 2017,
            "doi": "https://doi.org/10.48550/arXiv.1706.03762",
            "cited_by_count": 120000,
            "type": "article",
            "abstract_inverted_index": {"attention": [0], "need": [4]},
            "authorships": [{"author": {"display_name": "Ashish Vaswani"}}],
            "primary_location": {"source": {"display_name": "arXiv (Cornell University)"}},
            "open_access": {"is_oa": True, "oa_url": "https://arxiv.org/pdf/1706.03762"},
            "best_oa_location": {"pdf_url": "https://arxiv.org/pdf/1706.03762"},
        }
        hit = src._parse_work(work)
        assert hit.id == "openalex:W2741809807"
        assert hit.doi == "10.48550/arXiv.1706.03762"
        assert hit.abstract == "attention need"
        assert hit.url == "https://doi.org/10.48550/arXiv.1706.03762"
        assert hit.citations_count == 120000
        assert hit.open_access is True


class TestSemanticScholarParsing:
    def test_parse_paper(self):
        src = SemanticScholarSource()
        paper = {
            "paperId": "649def34-4858-4af4-8a2c-6d3f7d4b9b3a",
            "title": "BLOOM: A 176B-Parameter Open-Access Multilingual Language Model",
            "abstract": "Large language models have shown promise.",
            "year": 2023,
            "venue": "arXiv",
            "citationCount": 500,
            "externalIds": {"DOI": "10.48550/arXiv.2211.05100", "ArXiv": "2211.05100"},
            "openAccessPdf": {"url": "https://arxiv.org/pdf/2211.05100"},
            "url": "https://www.semanticscholar.org/paper/xyz",
            "authors": [{"name": "Teven Le Scao"}, {"name": "Angela Fan"}],
        }
        hit = src._parse_paper(paper)
        assert hit.id == "649def34-4858-4af4-8a2c-6d3f7d4b9b3a"
        assert hit.doi == "10.48550/arXiv.2211.05100"
        assert hit.authors == ["Teven Le Scao", "Angela Fan"]
        assert hit.open_access is True
        assert hit.extra["arxiv_id"] == "2211.05100"


class TestPubMedParsing:
    def test_parse_summary(self):
        src = PubMedSource()
        doc = {
            "uid": "32513646",
            "title": "A sample biomedical paper title",
            "pubdate": "2020 Jun 5",
            "fulljournalname": "Nature Medicine",
            "authors": [{"name": "John Smith"}, {"name": "Jane Roe"}],
            "articleids": [{"idtype": "doi", "value": "10.1038/s41591-020-0900-0"},
                           {"idtype": "pmc", "value": "PMC7299999"}],
        }
        hit = src._parse_summary(doc, {"32513646": "An abstract here."})
        assert hit.id == "32513646"
        assert hit.year == 2020
        assert hit.venue == "Nature Medicine"
        assert hit.abstract == "An abstract here."
        assert hit.doi == "10.1038/s41591-020-0900-0"
        assert hit.open_access is True
        assert hit.pdf_url == "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC7299999/"


# ---------------------------------------------------------------------------
# Mocked-HTTP search flows
# ---------------------------------------------------------------------------

class TestSearchAllAggregation:
    def test_unknown_source_raises(self):
        with pytest.raises(ValueError):
            search_all("anything", sources=["nope"])

    def test_skips_failing_source(self, monkeypatch):
        def boom(query, limit, year_from, year_to, sort, oa_only):
            raise RuntimeError("API down")

        def quiet(query, limit, year_from, year_to, sort, oa_only):
            return []
        monkeypatch.setattr(SOURCES["openalex"], "search", boom)
        monkeypatch.setattr(SOURCES["arxiv"], "search", quiet)  # keep test offline
        result = search_all("test", sources=["openalex", "arxiv"], limit=5)
        assert result["hits"] == []
        assert result["skipped"][0]["source"] == "openalex"
        assert result["skipped"][0]["reason"] == "error"

    def test_unified_hit_shape(self):
        hit = PaperHit(source="x", id="1", title="t", url="https://example.com")
        d = hit.to_dict()
        for field in ("source", "id", "title", "authors", "year", "venue",
                      "abstract", "doi", "url", "pdf_url", "citations_count",
                      "open_access", "type"):
            assert field in d

    def test_round_robin_interleaves_sources(self, monkeypatch):
        """A prolific source must not monopolize the result window."""
        def two_a(query, limit, year_from, year_to, sort, oa_only):
            return [PaperHit(source="arxiv", id=f"a{i}", title=f"A{i}", url="x")
                    for i in range(2)]

        def one_each(query, limit, year_from, year_to, sort, oa_only):
            return [PaperHit(source="openalex", id="o1", title="O1", url="x"),
                    PaperHit(source="crossref", id="c1", title="C1", url="x")]
        monkeypatch.setattr(SOURCES["arxiv"], "search", two_a)
        monkeypatch.setattr(SOURCES["openalex"], "search", one_each)
        monkeypatch.setattr(SOURCES["crossref"], "search", one_each)
        result = search_all("test", sources=["arxiv", "openalex", "crossref"], limit=4)
        sources = [h["source"] for h in result["hits"]]
        # first pass covers every source before any source repeats
        assert sorted(sources[:3]) == ["arxiv", "crossref", "openalex"]
        assert sources[3] == "arxiv"
        assert result["sources_queried"] == ["arxiv", "openalex", "crossref"]
