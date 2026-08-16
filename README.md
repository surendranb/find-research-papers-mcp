# Scientific Research Papers MCP Server 📄

> **Scientific literature grounding MCP server for AI agents: unified search across 250M+ scholarly papers on arXiv, PubMed, OpenAlex, CrossRef, and Semantic Scholar.**

[![PyPI version](https://img.shields.io/pypi/v/find-research-papers-mcp?label=PyPI&color=blue)](https://pypi.org/project/find-research-papers-mcp/)
[![PyPI downloads](https://img.shields.io/pypi/dm/find-research-papers-mcp?label=PyPI%20downloads&color=blue)](https://pypi.org/project/find-research-papers-mcp/)
[![npm version](https://img.shields.io/npm/v/find-research-papers-mcp?label=npm&color=red)](https://www.npmjs.com/package/find-research-papers-mcp)
[![npm downloads](https://img.shields.io/npm/dm/find-research-papers-mcp?label=npm%20downloads&color=red)](https://www.npmjs.com/package/find-research-papers-mcp)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Documentation](https://img.shields.io/badge/Docs-papers.builditwithai.xyz-purple)](https://papers.builditwithai.xyz)

🌐 **Live Documentation & Web Portal**: [https://papers.builditwithai.xyz](https://papers.builditwithai.xyz)

---

## ⚡ Quickstart

```bash
# 1-Line Universal Installer (Auto-configures Claude Code, Cursor, Claude Desktop & Antigravity)
curl -fsSL "https://papers.builditwithai.xyz/install" | bash

# Or run directly via your preferred runtime:
uvx find-research-papers-mcp
npx -y find-research-papers-mcp
```

---

## 🤖 Client Setup

### A. Claude Code (CLI)
```bash
claude mcp add papers -- uvx find-research-papers-mcp
```

### B. Cursor & Google Antigravity (`mcp.json`)
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

### C. Claude Desktop (`claude_desktop_config.json`)
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

### D. VS Code (Cline / Roo Code / Continue)
```json
{
  "mcpServers": {
    "papers": {
      "command": "npx",
      "args": ["-y", "find-research-papers-mcp"]
    }
  }
}
```

---

## 🛠️ Tools & Capabilities

| Tool Name | Parameters | Description | Return Type |
|---|---|---|---|
| `search_papers` | `query` (string), `sources` (list), `limit` (int) | Unified multi-index search across arXiv, PubMed, OpenAlex, CrossRef, Semantic Scholar. | `JSON / Markdown` |
| `get_paper` | `doi` (string) or `id` (string) | Retrieves paper metadata, abstract, authors, publication date, and open-access PDF link. | `JSON` |
| `get_references` | `doi` (string) | Fetches complete bibliography and referenced papers via CrossRef. | `JSON` |
| `get_citations` | `doi` (string) | Fetches citing papers and citation graph via OpenAlex. | `JSON` |
| `verify_paper` | `doi` (string) | HEAD-checks landing page accessibility and cross-checks retraction databases. | `JSON` |
| `list_sources` | *(none)* | Returns live status and latency metrics for all 5 scholarly indexes. | `JSON` |
| `skill_read` | `skill_name` (string) | Dynamically loads research methodology skills from GitHub. | `Markdown` |
| `skills_list` | *(none)* | Lists all available scientific research skills. | `JSON` |

---

## 🔒 Telemetry & Privacy

This package collects anonymous, non-PII diagnostic telemetry (command executions, latency, error codes) to improve tool reliability. No research queries, paper results, personal data, source code, or environment variables are ever collected or stored.

You can opt out anytime by setting either of the following environment variables:
```bash
export DO_NOT_TRACK=1
# or
export MCP_TELEMETRY_OPT_OUT=1
```

---

## 📄 License

MIT License. See [LICENSE](LICENSE) for details.
