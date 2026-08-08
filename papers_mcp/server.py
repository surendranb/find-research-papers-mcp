# SPDX-License-Identifier: Apache-2.0

"""Papers MCP — search & discover scholarly literature across arXiv, Semantic
Scholar, OpenAlex, Crossref, and PubMed. Metadata, references, and citations
are reachable even when the full text is paywalled."""

import time

from mcp.server.mcpserver import MCPServer

from . import telemetry
from .telemetry import send_telemetry

SERVER_NAME = "find-research-papers-mcp"
MCP_SERVER_VERSION = telemetry.MCP_SERVER_VERSION

INSTRUCTIONS = (
    "You can find scholarly grounding on any topic. search_papers returns "
    "papers from multiple sources (arXiv, OpenAlex, Crossref, Semantic Scholar, "
    "PubMed). get_paper resolves one paper and returns its references and "
    "citing works — this works even for paywalled journals (Nature etc.) "
    "because metadata and reference lists are public. Always include the url "
    "and doi with any paper you recommend. Before interpreting results, call "
    "get_research_method for the source-by-source rules and quirks."
)

mcp = MCPServer(SERVER_NAME, version=MCP_SERVER_VERSION, instructions=INSTRUCTIONS)
telemetry.announce_and_fire_boot_events()

_original_tool = mcp.tool


def _telemetry_tool(name=None, title=None, description=None, annotations=None,
                    icons=None, meta=None, structured_output=None):
    def decorator(func):
        import functools
        import inspect

        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            send_telemetry("tool_executed", {"tool_name": name or func.__name__})
            return await func(*args, **kwargs)

        wrapper.__signature__ = inspect.signature(func)  # type: ignore[attr-defined]
        return _original_tool(name, title=title, description=description,
                              annotations=annotations, icons=icons, meta=meta,
                              structured_output=structured_output)(wrapper)
    return decorator


mcp.tool = _telemetry_tool


@mcp.tool(title="Search research papers",
          description="Search scholarly literature across multiple sources "
                      "(arXiv, OpenAlex, Crossref, Semantic Scholar, PubMed)")
async def search_papers(query: str, sources: list[str] | None = None,
                        limit: int = 10, year_from: int | None = None,
                        year_to: int | None = None, sort: str = "relevance",
                        open_access_only: bool = False) -> dict:
    """Search scholarly literature across multiple sources.

    Args:
        query: topic or keywords (e.g. "retrieval augmented generation",
            "mitochondrial dynamics in neurons").
        sources: optional subset of source names (see list_sources).
            Defaults to all configured sources.
        limit: max results to return (default 10, max 50).
        year_from: only works published in/after this year.
        year_to: only works published in/before this year.
        sort: "relevance" (default), "citations", or "date".
        open_access_only: only include works with a free full-text link.

    Returns:
        hits: unified list of papers with id, title, authors, year, venue,
            abstract, doi, url, pdf_url, citations_count, open_access, source.
        skipped: sources that were unavailable (missing API key or error).
    """
    from .sources import search_all

    limit = max(1, min(int(limit), 50))
    if sort not in ("relevance", "citations", "date"):
        raise ValueError("sort must be one of: relevance, citations, date")
    t0 = time.monotonic()
    result = search_all(query, sources, limit, year_from, year_to, sort,
                        open_access_only)
    send_telemetry("tool_search", {
        "hits_count": len(result["hits"]),
        "sources_used": len(result["sources_queried"]),
        "skipped": len(result["skipped"]),
        "skipped_reasons": list({s["reason"] for s in result["skipped"]}),
        "latency_ms": int((time.monotonic() - t0) * 1000),
        "retracted_hits_count": sum(1 for h in result["hits"] if h.get("retracted")),
    })
    return result


@mcp.tool(title="Get paper details, references and citations",
          description="Resolve one paper by identifier and return its metadata "
                      "plus references (papers it cites) and citations (papers "
                      "citing it) — works even for paywalled papers")
async def get_paper(identifier: str, id_type: str = "auto",
                    include_references: bool = True,
                    include_citations: bool = True,
                    verify: bool = True) -> dict:
    """Resolve one paper and its reference/citation graph.

    Args:
        identifier: DOI (10.xxxx/...), arXiv id, PMID, OpenAlex id, or S2
            paperId. URLs (https://doi.org/..., arxiv.org/abs/...) also work.
        id_type: "auto" (default) guesses from the identifier, or one of:
            doi, arxiv, pmid, openalex, s2.
        include_references: include the papers this paper cites.
        include_citations: include papers citing this one (OpenAlex fallback
            for arXiv/DOI/PMID identifiers).
        verify: HEAD-check the landing page and cross-check the retraction
            flag (OpenAlex) — reported under verification, never fatal.

    Returns:
        paper: unified PaperHit for the paper itself.
        references: list of papers it cites.
        citations: list of papers citing it.
        verification: {resolves, retracted, checked_at} when verify=True.
        notes: explanations when a graph leg is unavailable.
    """
    from .sources import get_paper as _get_paper

    t0 = time.monotonic()
    result = _get_paper(identifier, id_type, include_references,
                        include_citations, verify)
    if "error" not in result:
        verification = result.get("verification") or {}
        send_telemetry("tool_get_paper", {
            "id_type": result.get("id_type"),
            "included_refs": include_references,
            "included_cites": include_citations,
            "verified": verify,
            "resolves": verification.get("resolves"),
            "retracted": verification.get("retracted"),
            "latency_ms": int((time.monotonic() - t0) * 1000),
        })
    return result


RESEARCH_METHOD = {
    "tiers": [
        {"tier": 1, "name": "broad discovery", "tools": ["search_papers"],
         "when": "unknown territory: let every source compete on the query"},
        {"tier": 2, "name": "deep dive", "tools": ["get_paper"],
         "when": "a specific paper, DOI, arXiv id, or PMID: metadata + "
                 "references + citations, even for paywalled journals"},
        {"tier": 3, "name": "verification", "tools": ["get_paper verify=true"],
         "when": "before citing or answering from a result: check "
                 "verification.resolves and verification.retracted"},
    ],
    "rules": [
        "Always pair a search hit with its url and doi when recommending it.",
        "Prefer hits whose abstract is non-empty and whose source is listed in "
        "the response — skipped sources mean that index did not answer.",
        "Do not fabricate citation counts, years, or authors: use the numbers "
        "the API returned, and treat None as unknown, not zero.",
        "A retracted=true hit must never be presented as valid evidence.",
    ],
    "quirks": [
        "Semantic Scholar 429s on the shared pool without a key — the server "
        "skips it and reports it under skipped; retry later or set "
        "FIND_RESEARCH_PAPERS_MCP_S2_API_KEY.",
        "OpenAlex abstracts are reconstructed from an inverted index; short or "
        "odd-spaced abstracts are the source's doing, not a bug.",
        "arXiv and PubMed expose no public citation graph: references/"
        "citations may be empty, with an OpenAlex fallback where indexed.",
        "Crossref cannot answer a bare-title lookup well; always search with "
        "keywords or a DOI.",
    ],
    "verify_steps": [
        "1. search_papers(query, sources=..., sort='citations') for the "
        "canonical works first.",
        "2. get_paper(identifier, include_references=True, "
        "include_citations=True, verify=True) on the top hit.",
        "3. Read verification: resolves=true means the landing page answers; "
        "retracted=true means OpenAlex flags it as retracted — stop there.",
        "4. If verification.resolves is null, the target was offline or "
        "bot-blocked: do not claim the paper is dead; say 'could not verify'.",
    ],
    "retraction_note": (
        "Retraction flags come from OpenAlex's is_retracted field and lag "
        "real-world retractions; absence of a flag is not proof of validity. "
        "The server never hides a retracted hit — it labels it."
    ),
}


@mcp.tool(title="Get research method",
          description="House method for using this server: tiers, rules, "
                      "source quirks, and verification steps")
async def get_research_method() -> dict:
    """Return the house research method: when to use each tool, rules for
    interpreting results, per-source quirks, and the verification steps.

    Returns:
        method: {tiers, rules, quirks, verify_steps, retraction_note}.
    """
    send_telemetry("tool_get_research_method", {})
    return {"method": RESEARCH_METHOD}


@mcp.tool(title="List paper sources",
          description="List every scholarly source the server can search, with "
                      "coverage, key requirements, and rate limits")
async def list_sources() -> list[dict]:
    """List every scholarly source the server can search: coverage, whether an
    API key is needed, rate limits, and whether it is currently configured."""
    from .sources import list_sources as _list

    listed = _list()
    send_telemetry("tools_listed", {})
    send_telemetry("tool_list_sources", {"sources_count": len(listed)})
    return listed


def main():
    send_telemetry("mcp_started", {})
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
