---
title: Research Papers MCP Setup & Configuration Guide
description: Step-by-step instructions for human operators and AI agents to configure find-research-papers-mcp, optional academic API keys, and client harnesses.
version: 1.0.0
---

# Research Papers MCP (`find-research-papers-mcp`) Setup Guide

Use this playbook to configure and optimize `find-research-papers-mcp` for scholarly literature discovery across arXiv, Semantic Scholar, OpenAlex, Crossref, and PubMed.

---

## 1. Quick Start (Zero-Auth by Default)

`find-research-papers-mcp` works **out-of-the-box with zero API keys**. All primary academic sources (arXiv, PubMed, OpenAlex, Crossref, Semantic Scholar) are queried using public endpoints.

Test basic connectivity:
- Call `list_sources()` to inspect live provider latency and status.
- Call `search_papers(query="quantum error correction", limit=5)` to test multi-source discovery.

---

## 2. Optional Academic API Keys (Higher Rate Limits)

If your workflow involves high-frequency literature mining or systematic reviews, configure optional API keys to lift rate limits:

- **Semantic Scholar API Key** (`SEMANTIC_SCHOLAR_API_KEY`):
  - Request key at: [Semantic Scholar API](https://www.semanticscholar.org/product/api)
  - Increases rate limits from 1 req/sec to 100 req/sec.
- **NCBI API Key** (`NCBI_API_KEY`):
  - Generate in NCBI account settings: [NCBI Account](https://www.ncbi.nlm.nih.gov/account/settings/)
  - Increases PubMed rate limits from 3 req/sec to 10 req/sec.
- **Springer Nature API Key** (`SPRINGER_NATURE_API_KEY`):
  - Request key at: [Springer Nature Developer Portal](https://dev.springernature.com/)

---

## 3. Client Harness Configuration

### Claude Desktop (`claude_desktop_config.json`)
```json
{
  "mcpServers": {
    "papers": {
      "command": "uvx",
      "args": ["find-research-papers-mcp"],
      "env": {
        "SEMANTIC_SCHOLAR_API_KEY": "<optional-key>",
        "NCBI_API_KEY": "<optional-key>"
      }
    }
  }
}
```

### Cursor (`.cursor/mcp.json`)
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

### CLI / NPX Passthrough
```bash
uvx find-research-papers-mcp
# or via npx
npx -y find-research-papers-mcp
```

---

## 4. Troubleshooting & Guidance

- **Rate Limits (HTTP 429)**: The server automatically falls back to secondary sources when one provider rate-limits. Call `skill_read('interpreting-errors')` for detailed provider-specific recovery.
- **Paywalled Papers**: `get_paper()` returns abstract, OpenAccess links, DOIs, and citations even when full text is publisher-restricted.
