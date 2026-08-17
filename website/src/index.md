---
layout: layout.njk
title: "Scientific Research Papers MCP Server"
description: "Unified scientific literature grounding across 250M+ papers on arXiv, PubMed, OpenAlex, CrossRef, and Semantic Scholar."
kicker: "SCIENTIFIC LITERATURE MCP"
subkicker: "Scholarly Grounding Engine"
header_badge: "250M+ Papers · arXiv · PubMed · OpenAlex · CrossRef · Citation Graph"
lede: "A Model Context Protocol (MCP) server for deep scientific research and academic literature grounding. Connects AI agents to 250M+ scholarly papers with citation graph traversal and unpaywalled PDF resolution."
chips:
  - "MCP 2.0"
  - "arXiv & PubMed"
  - "OpenAlex & CrossRef"
  - "PyPI: find-research-papers-mcp"
  - "TypeScript / Python"
toc:
  - id: "quickstart"
    title: "1. Universal 1-Line Quickstart"
  - id: "the-sources"
    title: "2. The 5 Scholarly Indexes"
  - id: "agent-setup"
    title: "3. AI Agent Integration"
  - id: "tools-reference"
    title: "4. Tool & Parameter Reference"
  - id: "citation-graph"
    title: "5. Citation Graph Traversal"
---

<section id="quickstart" class="space-y-6">
<div class="kicker">01 / Getting Started</div>

## Universal 1-Line Quickstart

Install and run `find-research-papers-mcp` across any modern agent runtime:

```bash
# ⚡ 1-Line Universal Installer (Auto-configures Claude Code, Cursor & Claude Desktop)
curl -fsSL https://papers.builditwithai.xyz/install | bash

# 🐍 Option 2: Run via Python (uvx)
uvx find-research-papers-mcp

# 📦 Option 3: Run via Node (npx)
npx -y find-research-papers-mcp
```

</section>

---

<section id="the-sources" class="space-y-6">
<div class="kicker">02 / Multi-Index Coverage</div>

## The 5 Scholarly Indexes

Instead of relying on LLM training weights that hallucinate citations, `find-research-papers-mcp` provides real-time verification across 250 million papers:

<div class="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
<div class="p-3.5 bg-[#fbfbfa] rounded-lg border border-[#e5e6e4] space-y-1">
<b>1. 📄 arXiv Preprints</b>
<p class="text-[#747982] leading-relaxed !mb-0">Instant access to latest preprints across CS, physics, mathematics, and quantitative biology with direct LaTeX and PDF extraction.</p>
</div>
<div class="p-3.5 bg-[#fbfbfa] rounded-lg border border-[#e5e6e4] space-y-1">
<b>2. 🧬 PubMed &amp; PMC</b>
<p class="text-[#747982] leading-relaxed !mb-0">Biomedical and life sciences literature from the National Library of Medicine with structured MeSH terms and clinical trial links.</p>
</div>
<div class="p-3.5 bg-[#fbfbfa] rounded-lg border border-[#e5e6e4] space-y-1">
<b>3. 🌐 OpenAlex Global Graph</b>
<p class="text-[#747982] leading-relaxed !mb-0">250M+ publications, author profiles, institutional affiliations, and concept taxonomies spanning all academic disciplines.</p>
</div>
<div class="p-3.5 bg-[#fbfbfa] rounded-lg border border-[#e5e6e4] space-y-1">
<b>4. 📑 CrossRef Metadata</b>
<p class="text-[#747982] leading-relaxed !mb-0">Authoritative DOI resolution, peer-reviewed journal metadata, funder registries, and publisher licensing data.</p>
</div>
</div>

</section>

---

<section id="agent-setup" class="space-y-6">
<div class="kicker">03 / Agent Integration</div>

## AI Agent Integration

Add `papers` to your agent environment:

### Claude Code CLI
```bash
claude mcp add papers -- uvx find-research-papers-mcp
```

### Cursor, Windsurf & Antigravity
Add to IDE settings:

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

### Claude Desktop
Add to `claude_desktop_config.json`:

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

</section>

---

<section id="tools-reference" class="space-y-6">
<div class="kicker">04 / API & Tools</div>

## Tool & Parameter Reference

| Tool Name | Parameters | Description |
|:---|:---|:---|
| `search_papers` | `query`, `sources`, `limit` | **Unified multi-index search** across arXiv, PubMed, OpenAlex, CrossRef, Semantic Scholar. |
| `get_paper` | `doi` or `id` | Retrieves paper metadata, abstract, authors, and open-access PDF link. |
| `get_references` | `doi` | Fetches complete bibliography and referenced papers via CrossRef. |
| `get_citations` | `doi` | Fetches citing papers and citation graph via OpenAlex. |
| `verify_paper` | `doi` | HEAD-checks landing page accessibility and cross-checks retraction databases. |
| `list_sources` | *(none)* | Returns live status and latency metrics for all 5 scholarly indexes. |

</section>

---

<section id="citation-graph" class="space-y-6">
<div class="kicker">05 / Deep Research</div>

## Citation Graph Traversal

AI models can traverse the forward and backward citation network in a single turn without manual re-prompting:

```bash
# Step 1: Discover foundational paper
papers.search_papers(query="Attention Is All You Need")

# Step 2: Traverse forward citations to find state-of-the-art descendants
papers.get_citations(doi="10.48550/arXiv.1706.03762", limit=5)
```

</section>
