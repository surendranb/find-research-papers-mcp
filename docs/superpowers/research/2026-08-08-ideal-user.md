# Ideal User Research — papers-mcp

Date: 2026-08-08 · Status: draft, pre-release · Linear: launch playbook SUR-92 (Phase 0 gate)

## Summary

papers-mcp is one aggregated search over the five key-free scholarly indexes
(arXiv, OpenAlex, Crossref, Semantic Scholar, PubMed) for AI agents and
humans. Its opinion: **verified citations, not hallucinated ones** — every
result is a real record from a live API, references/citations stay reachable
even for paywalled papers, and the caller never juggles five APIs, five rate
limiters, or five result shapes. This doc maps who needs that, what hurts
them (verified from the live Hermes skill set on this laptop), and how the
server answers each pain.

## Ideal users

| Persona | What they do | Why they need grounded papers |
|---|---|---|
| **Research agents (Hermes/Claude Code/Cursor agents)** | Daily literature research: run the `academic-literature-research` skill across arXiv/PubMed/S2/Crossref/OpenAlex, compile sourced reports | The skill is a 218-line manual of curl one-liners, source quirks, and fallback order — every search re-derives all of it |
| **AI-native builders** | Ship agents that cite papers (coaching systems, eval research, product research) | Their agents hallucinate titles/IDs; "verify before cite" is a discipline no agent reliably holds |
| **Humans doing lit review** | Researchers, engineers, analysts scanning CS/biomed literature | Multi-tab hunting across 5 sites with different UIs and auth is the status quo |

Secondary: anyone who wants to resolve a remembered paper to its DOI
(Crossref) or find citing works (OpenAlex `cites:`) without learning the
indexes.

## Verified pain evidence (from ~/.hermes, 2026-08-08)

The exact workflow this server automates exists and runs daily on this
laptop: `~/.hermes/skills/research/academic-literature-research/SKILL.md`
(218 lines), plus `research/arxiv/SKILL.md` and the "Daily Learning Summary"
cron job (`~/.hermes/cron/jobs.json`, `feed_aggregator.py`, 22 RSS feeds).
The skill's own `references/scholarly-apis.md` was written "2026-08-07 while
building papers-mcp" — it is the manual version of what the server does.

Pains, verbatim from the skill:

1. **Cardinal rule: all sources, always.** "Always search ALL available
   sources in parallel... A single-source search will be corrected."
   papers-mcp: one `search_papers` call round-robins 5 sources, dedupes,
   degrades per-source errors into `skipped` — never a lost search.
2. **Source quirks eat every session.** arXiv HTTP-only returns empty (must
   be HTTPS); S2 429s hard without a key (backoff `2s * attempt`, 3 tries);
   Crossref single-work route rejects `select` (400); OpenAlex abstracts are
   inverted indexes needing reconstruction; PubMed is a 3-step pipeline
   (esearch → esummary → efetch, abstracts live only in efetch). The skill
   documents each as a "don't waste time" pitfall — papers-mcp encodes them
   once, in the adapters.
3. **Hallucinated citations are a known failure mode.** "Never cite an arXiv
   ID from memory — verify with `id_list` first. Guessed IDs can resolve to
   unrelated papers" (documented case: remembered IDs returned a
   traffic-simulation paper and an optomechanics paper). Every model that
   cites from memory produces this. papers-mcp's `get_paper` returns only
   verified live records.
4. **Paywalled papers still have browsable metadata.** Crossref reference
   lists and OpenAlex citing-works are public metadata even when full text
   is paywalled — "that's how a Nature paper yields a browsable bibliography
   without full text." papers-mcp surfaces references/citations without
   needing publisher access.
5. **Setup and rate-limit friction.** Free S2 key = 100 req/5 min (optional,
   better limits); Google Scholar blocks programmatic access entirely and
   the skill says to not fight it. The opinion: if the platform offers a
   legitimate API/key, use it; never scrape, never skirt.

## How papers-mcp answers each

| Pain | Answer |
|---|---|
| Multi-source mandate | `search_papers` fans out to all 5 adapters in one call; round-robin interleave; per-source errors land in `skipped`, never break the aggregate |
| Source quirks | Encoded once in the adapters (HTTPS-only arXiv, S2 polite rate limiter + 429 retry, Crossref `select`-safe routes, OpenAlex inverted-index reconstruction, PubMed esearch→esummary→efetch) |
| Hallucinated citations | Every result is a live-API record with ID, URL, source; `get_paper` verifies by ID across sources; nothing is model-invented |
| Paywalled references | Crossref reference lists + OpenAlex `filter=cites:` give citations without full text |
| Setup friction | Zero-key out of the box; optional S2 key raises limits; one `list_sources` call tells the agent what's configured; single install line for human or agent |

## Market context (verified 2026-08-08)

- **Incumbent, single-source, strong:** `arxiv-mcp-server` (blazickjp) —
  3,030 stars, pushed 2026-07-29, ~79,800 PyPI downloads/month. It owns
  arXiv-only search, and is active. It does NOT aggregate sources, does NOT
  do references/citations, does NOT cover biomed.
- **Category is proven and getting used** (80k DLs/mo for the incumbent) —
  this is not dead space; demand exists.
- **Our named competitor is dead:** `research-papers-mcp` — one PyPI release
  (2026-06-01), 53 downloads/month, GitHub repo 404. Not a threat, not a
  validation.
- **Whitespace = the multi-source grounding layer:** no incumbent combines
  cross-source search + references/citations + paywall-proof metadata +
  zero-key setup. That is the opinion; arxiv-mcp-server is the counterfactual
  (what a single-source server can't do).

## Positioning

**Studio thesis (Surendran, 2026-08-08):**
1. There is a lot of great research out there.
2. It is not easily accessible to common folk — or even researchers/scholars.
3. We build an MCP that brings this to everyone.
4. LLMs are powerful but without precise instructions (skills or tools)
   they struggle to find the right knowledge — this is the differentiator.
5. This MCP addresses that problem statement.
6. Architected like the studio's other MCPs (ga4, gsc, wikipedia, music).
7. Anonymous telemetry drives continuous fixes.
8. Built and released open source.
9. No workarounds: we only make easier what a person can access normally —
   no scraping, no VPN-ing, no skirting paywalls. Every result comes from an
   official API a human could hit directly.

One line: **"Verified research papers for agents — every source, every
citation, no keys, no hallucinations."**

Differentiators: (1) 5 key-free sources, one call, round-robin + dedupe;
(2) references/citations reachable for paywalled papers; (3) zero-key setup,
optional S2 key when a platform offers one; (4) agent-first structured
output with per-result source attribution.

## Decisions this informs (before first release)

- **Dogfood first:** run papers-mcp against the exact Hermes workflows that
  motivated it — `academic-literature-research`, the arXiv skill, the daily
  research feed cron — and confirm it beats the curl-skill workflow.
- **Name:** pending (rename touches pyproject, server.json, package dir).
  Candidates verified free: `litsearch-mcp`, `paperfinder-mcp`,
  `sci-search-mcp`, `researchpapers-mcp`.
- **Point distribution content at research agents and AI-native builders,**
  not generic "MCP server" copy.
