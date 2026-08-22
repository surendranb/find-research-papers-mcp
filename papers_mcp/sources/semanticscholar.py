# SPDX-License-Identifier: Apache-2.0

"""Semantic Scholar source ("open scholar") — graph/v1 API.

Free key optional (FIND_RESEARCH_PAPERS_MCP_S2_API_KEY). Without a key the shared pool
429s under load, so this adapter enforces a polite inter-request interval,
retries 429s with backoff, and raises UnavailableError (-> 'skipped' in
search results) when the pool is exhausted.

Full references + citations graph, plus open-access PDF links.
"""

import os
import threading
import time

import requests

from .base import DEFAULT_HEADERS, PaperHit, Source, UnavailableError

API_URL = "https://api.semanticscholar.org/graph/v1"

_FIELDS = ("paperId,title,abstract,year,venue,citationCount,externalIds,"
           "openAccessPdf,url,authors,publicationTypes")

_KEY = os.getenv("FIND_RESEARCH_PAPERS_MCP_S2_API_KEY", "").strip()

# Polite pacing: with key ~1 req/3s is safe; without key the shared pool wants
# ~1 req/s. We stay conservative.
_INTERVAL = 0.4 if _KEY else 1.1


def set_session_api_key(key: str) -> None:
    """Apply an API key for THIS PROCESS ONLY (elicitation recovery flow).

    The value lives in module memory: it is never written to disk, never put
    in os.environ (child processes must not inherit it), and never sent to
    telemetry. Also retunes pacing and the list_sources status hint."""
    global _KEY, _INTERVAL
    _KEY = (key or "").strip()
    _INTERVAL = 0.4 if _KEY else 1.1
    SemanticScholarSource.requires_key = bool(not _KEY)
_LOCK = threading.Lock()
_LAST_REQUEST = 0.0

_SORT_MAP = {
    "relevance": None,  # search endpoint default ranking
    "citations": "citationCount:desc",
    "date": "publishedDate:desc",
}


class SemanticScholarSource(Source):
    name = "semanticscholar"
    display_name = "Semantic Scholar"
    description = "AI-built literature index with citations/references graph + TLDRs"
    coverage = "~220M papers across all disciplines (the 'open scholar')"
    requires_key = bool(not _KEY)
    key_hint = "FIND_RESEARCH_PAPERS_MCP_S2_API_KEY"
    rate_limit = "1 req/s shared pool (no key); 100 req/5min (free key)"

    def configured(self) -> bool:
        return True  # works key-free; key only raises limits

    def _get(self, path: str, params: dict) -> dict:
        global _LAST_REQUEST
        with _LOCK:
            wait = _INTERVAL - (time.time() - _LAST_REQUEST)
            if wait > 0:
                time.sleep(wait)
            _LAST_REQUEST = time.time()

        headers = dict(DEFAULT_HEADERS)
        if _KEY:
            headers["x-api-key"] = _KEY

        url = f"{API_URL}{path}"
        last_exc: Exception | None = None
        for attempt in range(3):
            try:
                resp = requests.get(url, params=params, headers=headers, timeout=10)
            except requests.RequestException as e:
                last_exc = e
                time.sleep(1 + attempt)
                continue
            if resp.status_code == 429:
                time.sleep(2 * (attempt + 1))  # backoff, then give up
                continue
            resp.raise_for_status()
            return resp.json()
        raise UnavailableError(f"semanticscholar rate limited or unreachable: {last_exc}")

    def _parse_paper(self, paper: dict) -> PaperHit:
        paper_id = str(paper.get("paperId") or "unknown")
        ext = paper.get("externalIds") or {}
        oa_pdf = paper.get("openAccessPdf") or {}
        authors = [a.get("name", "") for a in paper.get("authors") or []]
        authors = [a for a in authors if a]
        return PaperHit(
            source=self.name,
            id=paper_id,
            title=paper.get("title") or paper_id,
            authors=authors,
            year=paper.get("year"),
            venue=paper.get("venue") or "",
            abstract=paper.get("abstract") or "",
            doi=ext.get("DOI"),
            url=paper.get("url") or f"https://www.semanticscholar.org/paper/{paper_id}",
            pdf_url=oa_pdf.get("url"),
            citations_count=paper.get("citationCount"),
            open_access=bool(oa_pdf.get("url")),
            type="paper",
            extra={"arxiv_id": ext.get("ArXiv"), "pmid": ext.get("PubMed"),
                   "publication_types": paper.get("publicationTypes") or []},
        )

    def search(self, query: str, limit: int = 10, year_from: int | None = None,
               year_to: int | None = None, sort: str = "relevance",
               open_access_only: bool = False) -> list[PaperHit]:
        params: dict = {"query": query, "limit": max(1, min(limit, 100)), "fields": _FIELDS}
        if _SORT_MAP.get(sort):
            params["sort"] = _SORT_MAP[sort]
        data = self._get("/paper/search", params)
        hits = [self._parse_paper(p) for p in data.get("data", [])]
        if year_from or year_to:
            hits = [h for h in hits if h.year and (
                (not year_from or h.year >= year_from) and (not year_to or h.year <= year_to))]
        if open_access_only:
            hits = [h for h in hits if h.open_access]
        return hits

    def get(self, identifier: str, id_type: str = "auto") -> PaperHit | None:
        key = identifier.strip()
        if id_type == "doi":
            key = f"DOI:{key}"
        elif id_type == "arxiv":
            key = f"ArXiv:{key}"
        elif id_type == "pmid":
            key = f"PubMed:{key}"
        elif key.startswith("s2:"):
            key = key[len("s2:"):]
        data = self._get(f"/paper/{key}", {"fields": _FIELDS})
        return self._parse_paper(data)

    def _paper_id(self, identifier: str, id_type: str) -> str | None:
        if id_type == "s2" and not identifier.startswith(("DOI:", "ArXiv:", "PubMed:")):
            return identifier.strip()
        paper = self.get(identifier, id_type)
        return paper.id if paper else None

    def references(self, identifier: str, id_type: str = "auto", limit: int = 50) -> list[PaperHit]:
        pid = self._paper_id(identifier, id_type)
        if not pid:
            return []
        data = self._get(f"/paper/{pid}/references",
                         {"fields": "paperId,title,year,venue,externalIds,abstract",
                          "limit": max(1, min(limit, 100))})
        return [self._parse_paper(r.get("citedPaper", {})) for r in data.get("data", [])
                if r.get("citedPaper")]

    def citations(self, identifier: str, id_type: str = "auto", limit: int = 50) -> list[PaperHit]:
        pid = self._paper_id(identifier, id_type)
        if not pid:
            return []
        data = self._get(f"/paper/{pid}/citations",
                         {"fields": "paperId,title,year,venue,externalIds,abstract",
                          "limit": max(1, min(limit, 100))})
        return [self._parse_paper(c.get("citingPaper", {})) for c in data.get("data", [])
                if c.get("citingPaper")]
