# Scientific Research Papers MCP Server 📄

> **Scientific literature grounding MCP server for AI agents: unified search across 250M+ scholarly papers on arXiv, PubMed, OpenAlex, CrossRef, and Semantic Scholar.**

[![CI](https://github.com/surendranb/papers-mcp/actions/workflows/package-checks.yml/badge.svg)](https://github.com/surendranb/papers-mcp/actions)
[![PyPI version](https://img.shields.io/pypi/v/find-research-papers-mcp.svg?style=flat-square&color=blue)](https://pypi.org/project/find-research-papers-mcp/)
[![npm version](https://img.shields.io/npm/v/find-research-papers-mcp.svg?style=flat-square&color=red)](https://www.npmjs.com/package/find-research-papers-mcp)
[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/surendranb/papers-mcp/badge)](https://scorecard.dev/viewer/?site=github.com/surendranb/papers-mcp)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg?style=flat-square)](LICENSE)

🌐 **Live Documentation & Web Portal**: [https://papers.builditwithai.xyz](https://papers.builditwithai.xyz)

---

## ⚡ Quickstart

```bash
# 1-Line Universal Installer (Auto-configures Claude Desktop, Cursor, Claude Code, Antigravity, VS Code, Zed, Windsurf)
curl -fsSL "https://papers.builditwithai.xyz/install" | bash

# Or run directly via your preferred runtime:
uvx find-research-papers-mcp
npx -y find-research-papers-mcp
```

---

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
