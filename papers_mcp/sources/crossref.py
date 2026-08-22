# SPDX-License-Identifier: Apache-2.0

"""Crossref source — the DOI registry. No key required. Covers Springer Nature
and all registered publishers; every work carries a per-work reference list
(this is how Nature article references are reachable without full text).

- search(): query.bibliographic, year filter via from/until-pub-date
- get(): DOI resolution (id_type 'doi')
- references(): the work's reference list (titles/journals/DOIs)
- citations(): count via is-referenced-by-count; the actual citing list is
  served by OpenAlex (server falls back to it)
"""

import re

import requests

from .base import DEFAULT_HEADERS, PaperHit, Source

API_URL = "https://api.crossref.org/works"

_SELECT = ("DOI,title,author,issued,container-title,abstract,URL,publisher,"
           "is-referenced-by-count,type,link,score")
_SORT_MAP = {
    "relevance": "relevance",
    "citations": "is-referenced-by-count",
    "date": "published",
}

_JATS_TAG = re.compile(r"<[^>]+>")


def _strip_abstract(raw: str | None) -> str:
    """Crossref abstracts are JATS XML — reduce to plain text."""
    if not raw:
        return ""
    return re.sub(r"\s+", " ", _JATS_TAG.sub(" ", raw)).strip()


class CrossrefSource(Source):
    name = "crossref"
    display_name = "Crossref"
    description = "DOI registry for peer-reviewed journals (incl. Springer Nature)"
    coverage = "All DOI-registered journals & proceedings (Nature, Elsevier, IEEE, ACM...)"
    requires_key = False
    rate_limit = "50 req/s shared pool (polite: no key)"

    def _parse_item(self, item: dict) -> PaperHit:
        doi = str(item.get("DOI", ""))
        title = (item.get("title") or [""])[0]
        authors = []
        for a in item.get("author") or []:
            name = f"{a.get('given', '')} {a.get('family', '')}".strip()
            if name:
                authors.append(name)

        year = None
        issued = item.get("issued") or {}
        date_parts = issued.get("date-parts") or [[None]]
        if date_parts and date_parts[0]:
            year = date_parts[0][0]

        links = item.get("link") or []
        pdf_url = next((l.get("URL") for l in links
                        if "pdf" in (l.get("content-type") or "")), None)

        return PaperHit(
            source=self.name,
            id=doi,
            title=title or doi,
            authors=authors,
            year=year,
            venue=(item.get("container-title") or [""])[0],
            abstract=_strip_abstract(item.get("abstract") or ""),
            doi=doi,
            url=item.get("URL") or f"https://doi.org/{doi}",
            pdf_url=pdf_url,
            citations_count=item.get("is-referenced-by-count"),
            type=item.get("type") or "journal-article",
            extra={"publisher": item.get("publisher", "")},
        )

    def _get(self, params: dict) -> dict:
        resp = requests.get(API_URL, params=params, headers=DEFAULT_HEADERS, timeout=10)
        resp.raise_for_status()
        return resp.json()

    def search(self, query: str, limit: int = 10, year_from: int | None = None,
               year_to: int | None = None, sort: str = "relevance",
               open_access_only: bool = False) -> list[PaperHit]:
        params: dict = {
            "query.bibliographic": query,
            "rows": max(1, min(limit, 100)),
            "select": _SELECT,
            "sort": _SORT_MAP.get(sort, "relevance"),
            "order": "desc",
        }
        filters = []
        if year_from or year_to:
            filters.append(f"from-pub-date:{year_from or 1800}-01-01")
            filters.append(f"until-pub-date:{year_to or 9999}-12-31")
        if filters:
            params["filter"] = ",".join(filters)

        data = self._get(params)
        items = data.get("message", {}).get("items", [])

        hits = [self._parse_item(i) for i in items]
        if open_access_only:
            # Crossref has no true OA filter; presence of a full-text link is
            # the closest key-free proxy.
            hits = [h for h in hits if h.pdf_url or h.extra.get("publisher")]
        return hits

    def get(self, identifier: str, id_type: str = "auto") -> PaperHit | None:
        doi = identifier.strip()
        if doi.startswith("https://doi.org/"):
            doi = doi[len("https://doi.org/"):]
        elif doi.startswith("http://dx.doi.org/"):
            doi = doi[len("http://dx.doi.org/"):]
        elif doi.startswith("doi:"):
            doi = doi[len("doi:"):]
        if not re.match(r"^10\.\d{4,9}/", doi):
            return None
        try:
            # NOTE: the single-work route rejects the `select` param (search
            # route only) — fetch the full record and let _parse_item filter.
            resp = requests.get(f"{API_URL}/{doi}", headers=DEFAULT_HEADERS, timeout=10)
            resp.raise_for_status()
        except requests.RequestException:
            return None
        return self._parse_item(resp.json().get("message", {}))

    def references(self, identifier: str, id_type: str = "auto", limit: int = 50) -> list[PaperHit]:
        """The reference list of a DOI — this is how paywalled papers' citations
        become searchable: titles, journals, years, DOIs are public metadata."""
        doi = identifier.strip()
        if doi.startswith("https://doi.org/"):
            doi = doi[len("https://doi.org/"):]
        try:
            resp = requests.get(f"{API_URL}/{doi}", headers=DEFAULT_HEADERS, timeout=10)
            resp.raise_for_status()
        except requests.RequestException:
            return []
        refs = resp.json().get("message", {}).get("reference", [])
        out: list[PaperHit] = []
        for r in refs[:limit]:
            ref_doi = (r.get("DOI") or "").strip() or None
            title = r.get("article-title") or r.get("unstructured") or ""
            out.append(PaperHit(
                source=self.name,
                id=ref_doi or f"ref-{len(out)}",
                title=title[:400] or ref_doi or "untitled reference",
                authors=[r["author"]] if r.get("author") else [],
                year=r.get("year"),
                venue=r.get("journal-title") or "",
                doi=ref_doi,
                url=f"https://doi.org/{ref_doi}" if ref_doi else "",
                type="reference",
            ))
        return out
