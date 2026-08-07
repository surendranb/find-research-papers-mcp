# SPDX-License-Identifier: Apache-2.0

"""Papers MCP — search & discover scholarly literature across arXiv, Semantic
Scholar, OpenAlex, Crossref, and PubMed. Metadata, references, and citations
are reachable even when the full text is paywalled."""

from mcp.server.mcpserver import MCPServer

from . import telemetry
from .telemetry import send_telemetry

SERVER_NAME = "papers-mcp"
MCP_SERVER_VERSION = telemetry.MCP_SERVER_VERSION

INSTRUCTIONS = (
    "You can find scholarly grounding on any topic. search_papers returns "
    "papers from multiple sources (arXiv, OpenAlex, Crossref, Semantic Scholar, "
    "PubMed). get_paper resolves one paper and returns its references and "
    "citing works — this works even for paywalled journals (Nature etc.) "
    "because metadata and reference lists are public. Always include the url "
    "and doi with any paper you recommend."
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
    return search_all(query, sources, limit, year_from, year_to, sort,
                      open_access_only)


@mcp.tool(title="Get paper details, references and citations",
          description="Resolve one paper by identifier and return its metadata "
                      "plus references (papers it cites) and citations (papers "
                      "citing it) — works even for paywalled papers")
async def get_paper(identifier: str, id_type: str = "auto",
                    include_references: bool = True,
                    include_citations: bool = True) -> dict:
    """Resolve one paper and its reference/citation graph.

    Args:
        identifier: DOI (10.xxxx/...), arXiv id, PMID, OpenAlex id, or S2
            paperId. URLs (https://doi.org/..., arxiv.org/abs/...) also work.
        id_type: "auto" (default) guesses from the identifier, or one of:
            doi, arxiv, pmid, openalex, s2.
        include_references: include the papers this paper cites.
        include_citations: include papers citing this one (OpenAlex fallback
            for arXiv/DOI/PMID identifiers).

    Returns:
        paper: unified PaperHit for the paper itself.
        references: list of papers it cites.
        citations: list of papers citing it.
        notes: explanations when a graph leg is unavailable.
    """
    from .sources import get_paper as _get_paper

    return _get_paper(identifier, id_type, include_references, include_citations)


@mcp.tool(title="List paper sources",
          description="List every scholarly source the server can search, with "
                      "coverage, key requirements, and rate limits")
async def list_sources() -> list[dict]:
    """List every scholarly source the server can search: coverage, whether an
    API key is needed, rate limits, and whether it is currently configured."""
    from .sources import list_sources as _list

    send_telemetry("tools_listed", {})
    return _list()


def main():
    send_telemetry("mcp_started", {})
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
