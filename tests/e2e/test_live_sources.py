# SPDX-License-Identifier: Apache-2.0

"""Live smoke tests: hit real third-party APIs. Marked 'live' — run with
`pytest -m live`. Skipped automatically when the network is unavailable."""

import pytest

from papers_mcp.sources import SOURCES, get_paper, search_all

pytestmark = pytest.mark.live


@pytest.fixture(autouse=True)
def skip_without_network():
    import socket
    try:
        socket.create_connection(("api.openalex.org", 443), timeout=5).close()
    except OSError:
        pytest.skip("no network")


@pytest.mark.parametrize("source_name", ["arxiv", "openalex", "crossref", "pubmed"])
def test_live_search_each_source(source_name):
    src = SOURCES[source_name]
    hits = src.search("retrieval augmented generation", limit=3)
    assert len(hits) > 0, f"{source_name} returned no hits"
    for h in hits:
        assert h.id and h.title and h.url and h.source == source_name


def test_live_semantic_scholar_degrades_gracefully():
    """S2 shared pool 429s often without a key — must skip, not crash."""
    try:
        hits = SOURCES["semanticscholar"].search("machine learning", limit=3)
    except Exception:
        pytest.skip("semantic scholar shared pool rate-limited (no key)")
    assert all(h.id and h.title for h in hits)


def test_live_search_all_aggregation():
    result = search_all("mitochondrial dynamics", limit=5)
    assert len(result["hits"]) > 0
    for hit in result["hits"]:
        assert hit["id"] and hit["title"] and hit["url"] and hit["source"]


def test_live_get_paper_openalex_full_graph():
    data = get_paper("W2741809807", id_type="openalex",
                     include_references=True, include_citations=True)
    assert "error" not in data
    assert data["paper"]["title"]
    assert len(data["references"]) > 0
    assert len(data["citations"]) > 0
