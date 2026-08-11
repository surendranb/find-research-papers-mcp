# find-research-papers-mcp

[![PyPI version](https://img.shields.io/pypi/v/find-research-papers-mcp?label=PyPI)](https://pypi.org/project/find-research-papers-mcp/)
[![PyPI downloads](https://img.shields.io/pypi/dm/find-research-papers-mcp?label=PyPI%20downloads)](https://pypi.org/project/find-research-papers-mcp/)
[![npm version](https://img.shields.io/npm/v/find-research-papers-mcp?label=npm)](https://www.npmjs.com/package/find-research-papers-mcp)
[![npm downloads](https://img.shields.io/npm/dm/find-research-papers-mcp?label=npm%20downloads)](https://www.npmjs.com/package/find-research-papers-mcp)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)

Give your AI agent scientific grounding: search **250M+ scholarly works**
across five indexes with one query, and pull references and citations even
from paywalled journals.

LLMs hallucinate citations. This server replaces guesswork with verified
metadata — every hit is a real record from a real scholarly index, with a DOI,
a URL, an abstract, and a retraction flag when the source knows one.

## What it does

- **One search, five indexes** — arXiv, OpenAlex, Crossref, PubMed, and
  Semantic Scholar, aggregated into a single hit schema. The same query goes
  out everywhere; results come back unified.
- **Paywalled papers, public bibliography** — a Nature or IEEE paper you
  cannot read still has public metadata: `get_paper` returns its references
  (Crossref) and citing works (OpenAlex). DOI, abstract, and reference data
  are public even when full text is not.
- **Verification built in** — `verify=true` HEAD-checks the landing page and
  cross-checks OpenAlex's retraction flag. A paper that won't answer is
  reported as `resolves: null` (unknown), never as "dead".
- **Graceful degradation** — a rate-limited or failing source is skipped and
  reported in the response's `skipped` list. No key required anywhere; one
  source's outage never breaks a search.
- **Zero required API keys** — works out of the box. An optional Semantic
  Scholar key lifts its shared-pool rate limit.

## Sources

| Source | Coverage | Key needed |
|---|---|---|
| `arxiv` | Open-access preprints (CS, physics, math, q-bio, q-fin, stats) | no |
| `openalex` | ~250M scholarly works — Nature and all peer-reviewed journals | no |
| `crossref` | DOI registry — Springer Nature, Elsevier, IEEE, ACM… | no |
| `pubmed` | 30M+ biomedical citations, free full-text via PMC | no |
| `semanticscholar` | ~220M papers, citation graph + TLDRs | optional¹ |

¹ Semantic Scholar's shared pool rate-limits without a key. Set
`FIND_RESEARCH_PAPERS_MCP_S2_API_KEY` to lift it. When a source is skipped,
the server says so in the response — it never crashes.

## Tools

| Tool | What it does |
|---|---|
| `search_papers(query, sources, limit, year_from, year_to, sort, open_access_only)` | Aggregate search across all or selected sources. Returns unified hits: `id, title, authors, year, venue, abstract, doi, url, pdf_url, citations_count, open_access, retracted, type, source`. |
| `get_paper(identifier, id_type, include_references, include_citations, verify)` | Resolve one paper by DOI, arXiv ID, PMID, OpenAlex ID, or S2 ID (auto-detected), plus its reference and citation graph — works for paywalled papers. With `verify=true` (default), adds `verification: {resolves, retracted, checked_at}`. |
| `get_research_method()` | The house method: when to use each tool, rules for interpreting results, per-source quirks, verification steps. Agents should call this before interpreting results. |
| `list_sources()` | What is searchable and from where. |

## Install

**Any MCP client** (Claude Code, Cursor, opencode, …):

```bash
uvx find-research-papers-mcp        # or
npx -y find-research-papers-mcp
```

**One-command installer** (served from a Cloudflare worker — auto-detects uvx
vs npx, finds your harness, merges into the right config, and reports
anonymous install telemetry back to the worker — Claude Code, Cursor,
opencode, Windsurf, VS Code):

```bash
curl -fsSL https://papers-mcp-install-telemetry.reachsuren.workers.dev/install?src=readme | bash
# or explicitly:  bash install.sh --claude   bash install.sh --opencode
```

**Claude Code plugin** (one-time registration, then install from anywhere):

```
/plugin marketplace add surendranb/find-research-papers-mcp
/plugin install find-research-papers@find-research-papers-mcp
```

**Official MCP Registry** — the server is listed as
`io.github.surendranb/find-research-papers-mcp`, installable through clients
that support the registry.

**From source:**

```bash
uv venv .venv --python 3.11
uv pip install --python .venv/bin/python -e .
.venv/bin/python -m papers_mcp          # stdio server
```

**Optional config:** `export FIND_RESEARCH_PAPERS_MCP_S2_API_KEY=...` for
full-rate Semantic Scholar.

## Quick start

```python
# search everything at once
hits = search_papers("retrieval augmented generation", limit=3)
# -> unified hits: id, title, authors, year, doi, url, pdf_url,
#    citations_count, abstract, retracted, source

# deep-dive one paper, even paywalled
paper = get_paper("10.1038/s41586-023-06466-1",
                  include_references=True, include_citations=True)

# verify before you cite
v = get_paper(identifier, verify=True)["verification"]
# v["resolves"]: landing page answered?
# v["retracted"]: OpenAlex flags this paper as retracted?
```

A `retracted: true` hit must never be presented as evidence.

## Telemetry & privacy

The server collects **anonymous usage telemetry**, on by default, to learn
which sources and features matter.

- **Sent:** event names, an anonymous installation UUID, coarse environment
  signals (OS, Python version, agent name), and tool outcome counts (hits
  found, sources used, skipped reasons, retracted hits, latency).
- **Never sent:** search queries, paper results, file paths, emails, or URLs.
- **Opt out** with any of: `FIND_RESEARCH_PAPERS_MCP_TELEMETRY=false`,
  `DISABLE_TELEMETRY=1`, `DO_NOT_TRACK=1`, `NO_TELEMETRY=1`.
  The install ID lives in `~/.find_research_papers_mcp/installation_id`;
  delete the folder to reset it.
- The first run prints a disclosure to stderr before anything is sent.
- Telemetry never blocks or slows the server: a dead endpoint just drops
  events.

## Development

```bash
.venv/bin/python -m pytest tests/test_sources.py          # offline unit tests
.venv/bin/python -m pytest tests/e2e/test_e2e.py          # native MCP protocol
.venv/bin/python -m pytest -m live tests/e2e/             # live third-party APIs
```

## License

Apache-2.0
