# AGENTS.md — Codebase Operational Guide for AI Agents

> **Context, architecture, file map, and execution commands for AI coding agents (Claude Code, Cursor, Codex, Gemini, Antigravity, OpenCode, Aider) working on `papers-mcp`.**

---

## 1. Codebase Overview

- **Language & Runtime**: Python 3.10+ (`mcp` FastMCP, `httpx`, `pydantic`, `xmltodict`).
- **Package Name**: `find-research-papers-mcp` (PyPI) / `find-research-papers-mcp` (NPM thin wrapper).
- **Core Function**: Unified scientific literature search and grounding engine across 5 major scholarly indexes: arXiv, PubMed, OpenAlex, CrossRef, and Semantic Scholar.

---

## 2. Directory & File Map

```
papers-mcp/
├── papers_mcp/
│   ├── server.py              # FastMCP server, tools (search_papers, get_paper, get_references, get_citations)
│   ├── telemetry.py           # Edge Schema v2 telemetry client
│   └── sources/
│       ├── base.py            # Abstract BaseSource provider interface
│       ├── arxiv.py           # arXiv API connector (Atom XML / REST)
│       ├── pubmed.py          # NCBI PubMed E-Utilities connector
│       ├── openalex.py        # OpenAlex academic graph & citation API connector
│       ├── crossref.py        # CrossRef DOI metadata & reference connector
│       └── semanticscholar.py # Semantic Scholar Academic Graph API connector
├── npm/                       # Thin Node.js CLI launcher
│   ├── bin/index.js           # Subprocess wrapper spawning uvx find-research-papers-mcp
│   └── package.json           # NPM package metadata
├── tests/                     # Unit and integration test suite
│   ├── test_server.py         # FastMCP tools tests
│   └── test_sources.py        # Scholarly API connector tests
├── pyproject.toml             # Python packaging metadata (find-research-papers-mcp)
├── smithery.yaml              # Smithery.ai marketplace configuration
├── server.json                # Official MCP registry specification
├── gemini-extension.json      # Google Gemini / Antigravity extension manifest
├── .claude-plugin/            # Claude Code plugin manifests (plugin.json, marketplace.json)
└── .well-known/ai-plugin.json # OpenAI / ChatGPT Actions manifest
```

---

## 3. Development & Testing Commands

```bash
# Install dependencies in editable mode
uv sync || pip install -e ".[dev]"

# Run the MCP server locally in stdio mode
uv run python -m papers_mcp.server

# Run the test suite
uv run pytest tests/ -v

# Run linting
uv run ruff check .
```

---

## 4. Tool Implementation Invariants & Gotchas

1. **DOI Normalization**:
   - `doi` strings can be passed in various formats (`10.1038/s41586-020-2649-2`, `https://doi.org/...`, `doi:10...`). Normalize all inputs to clean standard DOI format `10.xxxx/xxxx` before querying CrossRef or OpenAlex.
2. **Parallel Source Execution (`search_papers`)**:
   - `search_papers` queries sources concurrently using `asyncio.gather(..., return_exceptions=True)`. If one index (e.g. Semantic Scholar) rate-limits, the tool must return results from the other 4 sources without failing the entire request.
3. **Open-Access PDF Links**:
   - `get_paper` prioritizes direct open-access PDF URLs from arXiv, Unpaywall, or PubMed Central.
