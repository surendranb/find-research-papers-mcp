# find-research-papers-mcp

MCP server for **scientific grounding**: search and discover open-source
research papers and scholarly literature across five sources, and pull
references/citations from paywalled journals (Nature, Elsevier, IEEE, ACM…)
even when the full text is not readable — DOI/abstract/reference metadata is
public.

Built to the house pattern (local stdio Python/FastMCP — same architecture as
[music-mcp](https://linear.app/surendran/project/mcp-server-production-launch-playbook-f266b3489617/issues/SUR-253)).

## Sources

| Source | What it covers | Key needed |
|---|---|---|
| `arxiv` | Open-access preprints (CS, physics, math, q-bio, q-fin, stats) | no |
| `openalex` | ~250M scholarly works — Nature + all peer-reviewed journals | no |
| `crossref` | DOI registry — Springer Nature, Elsevier, IEEE, ACM… | no |
| `pubmed` | 30M+ biomedical citations, free full-text via PMC | no |
| `semanticscholar` | ~220M papers, citation graph + TLDRs ("open scholar") | optional¹ |

¹ Semantic Scholar's shared pool 429s without a key. Set
`RESEARCH_MCP_S2_API_KEY` in the server's environment to lift the limit. All
sources degrade gracefully: a failing/rate-limited source is skipped and
reported in the response's `skipped` list, never a crash.

## Tools

- **`search_papers(query, sources, limit, year_from, year_to, sort, open_access_only)`**
  — aggregate search across all (or chosen) sources with a unified hit schema:
  `id, title, authors, year, venue, abstract, doi, url, pdf_url,
  citations_count, open_access, type, source`.
- **`get_paper(identifier, id_type, include_references, include_citations)`** —
  resolve one paper by DOI / arXiv ID / PMID / OpenAlex ID / S2 ID (auto-detected
  from the identifier), plus its **references** and **citations** — this is how
  a paywalled Nature paper still yields a browsable bibliography: Crossref
  provides the reference list, OpenAlex the citing works.
- **`list_sources()`** — discovery: what is searchable and from where.

## Install & run

```bash
uv venv .venv --python 3.11
uv pip install --python .venv/bin/python -e .
.venv/bin/python -m papers_mcp          # stdio server
```

Optional: `export RESEARCH_MCP_S2_API_KEY=...` to enable full-rate Semantic
Scholar.

## Telemetry & Privacy

find-research-papers-mcp collects **anonymous usage telemetry** (SUR-86 Phase 2), on by
default, matching the house pattern:

- **What is sent**: event names + an anonymous installation UUID + coarse
  environment signals (OS, Python version, agent name like claude_code/cursor,
  run context, discovery channel). **Never** search queries, paper results,
  file paths, emails, URLs, or client metadata values.
- **Events**: `server_first_install`, `package_download` (once per version),
  `mcp_started`, `tools_listed`, `tool_executed` (tool name only).
- **Where**: a Cloudflare worker gateway
  (`FIND_RESEARCH_PAPERS_MCP_TELEMETRY_URL`, defaults to the find-research-papers-mcp worker; deployed in
  Phase 4). Opt-out or a dead URL simply means events are dropped — telemetry
  never blocks or slows the server.
- **Opt out** any of: `FIND_RESEARCH_PAPERS_MCP_TELEMETRY=false`, `DISABLE_TELEMETRY=1`,
  `DO_NOT_TRACK=1`, `NO_TELEMETRY=1`. The install ID lives in
  `~/.find_research_papers_mcp/installation_id`; delete the folder to reset it.

The first run prints a short disclosure to stderr before anything is sent.

## Wire into Hermes

Add to `~/.hermes/config.yaml` under `mcp_servers:` (see AGENTS.md), then
restart the gateway. `search_papers` / `get_paper` / `list_sources` then
appear as native tools.

## Tests

```bash
.venv/bin/python -m pytest tests/test_sources.py          # offline unit tests
.venv/bin/python -m pytest tests/e2e/test_e2e.py          # native MCP protocol
.venv/bin/python -m pytest -m live tests/e2e/             # live third-party APIs
```

## Playbook status

- [x] Phase 0 — brand scouting (`scripts/scout_mcp_brand.py`; PyPI/GitHub clear,
      npm collision on `find-research-papers-mcp` noted for Phase 3 — `open-scholar-mcp` is
      the fully-clear fallback)
- [x] Phase 1 — core server (this repo, branch `feat/phase-1-core-server`)
- [x] Phase 2 — telemetry (anonymous, opt-out, e2e-verified against a local
      capture gateway; worker deploy is Phase 4)
- [ ] Phase 3 — packaging/manifest (`server.json` here is a first draft)
- [ ] Phase 6 — production wiring (SUR-85 / playbook issue tracker)
