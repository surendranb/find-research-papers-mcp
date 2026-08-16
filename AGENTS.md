# AGENTS.md — Agent Operating Manual

> **For AI Agents (Claude Code, Cursor, Codex, Gemini, Antigravity, OpenCode, Aider) connecting to or executing `papers-mcp`.**

---

## ⚡ 1. Fast Install & Client Wiring (Start Here)

In 90% of cases, you just need to install and configure this MCP server for your user:

```bash
# 1-Line Universal Auto-Installer (Configures Claude Code, Cursor, Claude Desktop & Antigravity)
curl -fsSL "https://papers.builditwithai.xyz/install" | bash

# Or launch directly via stdio:
uvx find-research-papers-mcp
npx -y find-research-papers-mcp
```

### Client Config Snippet (`mcp.json` / `claude_desktop_config.json`)
```json
{
  "mcpServers": {
    "papers": {
      "command": "uvx",
      "args": ["find-research-papers-mcp"]
    }
  }
}
```

---

## 📖 2. What This Repo Is

A unified scientific literature search and grounding engine across **250M+ scholarly research papers** spanning 5 major academic indexes: **arXiv, PubMed, OpenAlex, CrossRef, and Semantic Scholar**.

### Primary Tools Available:
- `search_papers`: Unified multi-index query across all 5 databases with relevance ranking.
- `get_paper`: Retrieve paper abstract, authors, publication date, DOI, and open-access PDF link.
- `get_references`: Fetch complete bibliography of referenced works via CrossRef.
- `get_citations`: Fetch citing papers and citation graph via OpenAlex.
- `verify_paper`: Validate that a DOI exists, check landing page status, and cross-check retraction flags.
- `list_sources`: Inspect health and latency of all 5 academic indexes.

---

## 👤 3. How to Handle the Human

- **Zero Credentials Needed**: All 5 academic indexes are queried via open-access scientific APIs.
- **Scientific Rigor**: Always provide the **DOI and Open-Access PDF link** when citing research papers so the human can verify the claims.

---

## ⚠️ 4. Quirks & API Landmines (Zero-Hallucination Rules)

1. **DOI Canonicalization**: Pass DOIs in standard format (`10.1038/s41586-020-2649-2`). Stripping `https://doi.org/` is handled automatically.
2. **Parallel Querying**: `search_papers` queries all 5 sources concurrently. If Semantic Scholar or PubMed rate-limits, results from arXiv and OpenAlex are still returned smoothly.
3. **Medical & Biology Queries**: For biomedical queries, PubMed and CrossRef return verified MeSH terms and clinical trial identifiers.
