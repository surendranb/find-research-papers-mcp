# Papers MCP — Local stdio server design

SUR-85 (Playbook Phase 1) · 2026-08-07 · Local stdio MCP server (house pattern: google-analytics-mcp, google-search-console-mcp, music-mcp). Remote later (per user: "eventually we may make it remote to regularly update the source list").

## Outcome

"Papers MCP looks like: an MCP server that gives any student, researcher, or curious person a searchable way to **get scientific grounding on any topic** — search & discover open-source research papers and scholarly literature (arXiv, Semantic Scholar 'open scholar', Nature + other peer-reviewed journals via OpenAlex/Crossref/PubMed), where **metadata, references, and citations are reachable even when the full text is paywalled or unreadable**."

## Architecture

Python + MCP SDK 2.x (`mcp.server.mcpserver.MCPServer`, stdio transport). Monorepo mirroring `music-mcp`:

```
papers-mcp/
├── pyproject.toml            # name "papers-mcp", scripts "papers-mcp", "papers-mcp-server"
├── server.json               # io.github.surendranb/papers-mcp (schema 2025-12-11)
├── papers_mcp/
│   ├── server.py             # MCPServer, tools: search_papers, get_paper, list_sources
│   ├── sources/
│   │   ├── base.py           # Source ABC: search()/get()/references()/citations() -> PaperHit
│   │   ├── arxiv.py          # export.arxiv.org Atom API, no key
│   │   ├── openalex.py       # api.openalex.org/works, no key (polite pool mailto)
│   │   ├── crossref.py       # api.crossref.org/works, no key
│   │   ├── semanticscholar.py# graph/v1, free key optional (RESEARCH_MCP_S2_API_KEY), polite limiter
│   │   └── pubmed.py         # NCBI eutils esearch + esummary, no key
├── tests/
│   ├── test_sources.py       # mocked-HTTP adapter tests
│   └── e2e/
│       ├── test_e2e.py       # native MCP protocol round-trip (spawn real server)
│       └── test_live_sources.py  # live API smoke (marked "live")
├── docs/superpowers/specs/
└── README.md, AGENTS.md
```

No telemetry in Phase 1 (playbook Phase 2, SUR-86). No distribution (Phase 3, SUR-87).

## Tools

- `search_papers(query, sources?, limit?, year_from?, year_to?, sort?, open_access_only?)` — aggregate search across configured sources, unified hit: `id, title, authors, year, venue, abstract, doi, url, pdf_url, source, citations_count, open_access, type`. Returns `{hits, skipped}` (skipped = unavailable sources, per music pattern).
- `get_paper(identifier, id_type?, include_references?, include_citations?)` — paper details + **references + citations**. This is how peer-reviewed (Nature etc.) metadata is reachable without reading the paywalled full text: Crossref/OpenAlex/S2 expose title/authors/venue/DOI/reference lists publicly.
- `list_sources()` — every source: coverage, key requirement, rate limit, configured.

### id_type resolution (`get_paper`)

`auto` guess → explicit: `doi` (Crossref metadata + references; OpenAlex citations fallback), `arxiv`, `pmid`, `openalex` (full refs+cites), `s2` (full refs+cites). Normalizes `https://doi.org/…`, `doi:`, `arxiv.org/abs/…` prefixes.

## Source matrix

| Source | Type | Access | Covers | Refs | Cites |
|---|---|---|---|---|---|
| arXiv | live, no key | Atom API (HTTPS — plain HTTP returned empty) | CS/physics/math preprints | — | — |
| OpenAlex | live, no key | `/works` + polite pool `mailto=` | ~250M works, Nature + all peer-reviewed journals | ✅ | ✅ |
| Crossref | live, no key | REST `/works` | DOI registry, Springer Nature publishers, per-work references | ✅ | count only (OpenAlex fallback for list) |
| Semantic Scholar | live, free key optional | graph/v1 | citations/references graph, TLDRs | ✅ | ✅ |
| PubMed | live, no key | eutils esearch+esummary | biomedical (MEDLINE) | — | — |

Springer Nature API needs a key; OpenAlex + Crossref already cover Nature metadata key-free → no key-gated source in Phase 1.

## Unified schema (PaperHit)

`source, id, title, authors[], year, venue, abstract, doi, url, pdf_url, citations_count, open_access, type, extra{}` — every hit must carry `id`, `title`, `url`, `source` non-empty (verification assertion).

## Config

| Env | Purpose | Required |
|---|---|---|
| RESEARCH_MCP_S2_API_KEY | Semantic Scholar free key (higher rate limits) | no |
| RESEARCH_MCP_TELEMETRY=false | opt-out (Phase 2) | no |

Missing key → source skipped at runtime, listed in `list_sources` as "key required". S2 without key uses a polite 1 rps limiter + 429 retry/backoff and degrades to skipped when the shared pool is exhausted.

## Verification

1. Native MCP protocol e2e: spawn real server (`uv run papers-mcp`) → JSON-RPC `initialize` → `tools/list` → `tools/call list_sources` → `tools/call search_papers` → `tools/call get_paper` (doi with references+citations) → assert response id matching + unified schema (id/title/url/source non-empty).
2. Live smoke per source (`pytest -m live`).
3. Wire into Hermes `config.yaml` (`mcp_servers.papers_mcp`, venv python + `-m papers_mcp`, tools.include) → `hermes gateway restart` → call `mcp__papers_mcp__*` from a live session.
4. Linear: close-out comment on SUR-85 with evidence.
