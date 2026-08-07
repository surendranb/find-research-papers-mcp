# AGENTS.md — conventions for this repo

House pattern (music-mcp / playbook). Read before working here.

## Stack

- Python 3.11, FastMCP (`mcp>=2.0.0`) via `uv`.
- Local stdio server only (Phase 1). No HTTP/SSE transport yet.
- `requests` for third-party APIs — no async HTTP client.

## Layout

```
papers_mcp/
  server.py          # MCPServer entry point + tool definitions
  sources/
    base.py          # PaperHit schema + Source ABC (unified contract)
    arxiv.py         # export.arxiv.org Atom API
    openalex.py      # api.openalex.org/works (abstract reconstruction, cites filter)
    crossref.py      # api.crossref.org/works (JATS abstract stripping)
    semanticscholar.py  # graph/v1 API (polite rate limiter, 429 retry)
    pubmed.py        # NCBI E-utilities (esearch → esummary + efetch)
    __init__.py      # SOURCES registry + search_all() + guess_id_type()
tests/
  test_sources.py      # offline unit tests (mocked HTTP / pure functions)
  e2e/test_e2e.py      # native MCP JSON-RPC over stdio (spawns real binary)
  e2e/test_live_sources.py  # -m live: real third-party API smoke
```

## Rules

- New source = subclass `Source` in `sources/<name>.py`, register in
  `SOURCES`, add to `list_sources` tests + live smoke. Unified `PaperHit`
  schema is mandatory — no per-source shapes.
- Never let one failing source break a search: `search_all` catches per-source
  errors into `skipped`, `get_paper` returns a structured `{"error": ...}`
  dict (no exceptions across the MCP boundary).
- API changes break quietly: verify live (`pytest -m live`) after touching
  adapters. Historical gotchas: Crossref single-work route rejects `select`;
  OpenAlex `cited_by_api_url` is deprecated (use `filter=cites:W...`);
  arXiv only over HTTPS; Semantic Scholar 429s without a key.
- Update `docs/superpowers/specs/` design doc when behavior changes.
- Auto-generated comment in every file (see headers) — update on edit.

## Verification

```bash
.venv/bin/python -m pytest tests/               # everything incl. live
.venv/bin/python -m pytest tests/test_sources.py -q   # offline only
```
