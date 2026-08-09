---
title: Interpreting errors
description: How to read this server's error and skipped shapes (search_papers, get_paper) and recover
---

# Interpreting errors from find-research-papers-mcp

Factual guide to every error shape this server produces, and the recovery
move for each. Errors here are structured data, not crashes — read them.

## search_papers

A search never hard-fails on a single source. Failures appear in `skipped`:

- `{"source": ..., "reason": "key_required", "hint": ...}` — that source
  needs an API key the user has not configured. Recovery: proceed with the
  hits you got (other sources answered); mention the hint's env var only if
  the user asks for that specific source's coverage.
- `{"source": ..., "reason": "error", "detail": ...}` — the source's API
  failed (timeout, 429, 5xx). Semantic Scholar 429s on the shared pool
  without a key — this is normal, not a bug. Recovery: use the remaining
  hits; retry later only if that source is essential to the question.

The call itself raises (protocol `isError: true`) only for bad arguments:

- `sort must be one of: relevance, citations, date` — fix the `sort` value.
- `unknown source(s): ... Known: ...` — fix the `sources` list to names
  from `list_sources`.

`hits: []` with nothing skipped means the query genuinely matched nothing:
broaden keywords; do not invent results.

## get_paper

Error-shaped results are dicts with an `error` key:

- `unknown id_type '...'` — fix `id_type` to one of: doi, arxiv, pmid,
  openalex, s2 (or use "auto").
- `paper not found via <Source> (id_type=..., identifier=...)` — the owning
  source has no record. Recovery: check the identifier for typos; if it was
  guessed by `id_type: auto`, pass the correct `id_type` explicitly; or
  search_papers for the title instead.

Successful results can still carry degraded legs, reported in `notes`:

- `references unavailable: ...` / `citations unavailable: ...` — that leg's
  API failed; the paper itself is valid.
- `<Source> does not expose a public reference list` — arXiv and PubMed have
  no public reference graph; this is a source limit, not a failure.
- `citing works not available from this source (OpenAlex fallback applies
  when the work is indexed there)` — empty citations may mean "not indexed",
  never "never cited".

## verification (get_paper verify=true)

- `resolves: true` — landing page answers; `false` — 404/410, likely dead
  identifier; `null` — target offline or bot-blocked: say "could not
  verify", never claim the paper is dead.
- `retracted: true` — never present the paper as valid evidence.
- `retracted: null` — retraction status unknown (OpenAlex does not index
  it); absence of a flag is not proof of validity.

## skills

- `Skill '...' not found` — call `skills_list` and use an exact name.
- `temporarily unavailable` — fetch failed; proceed with tool docstrings
  and `get_research_method`.
