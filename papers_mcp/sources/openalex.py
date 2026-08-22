# SPDX-License-Identifier: Apache-2.0

"""OpenAlex source — the largest open scholarly index (~250M works), covering
Nature and essentially every peer-reviewed journal. No key required (polite
pool via mailto). Full metadata + references + citations.

- abstract is served as an inverted index -> reconstructed in _reconstruct_abstract
- references(): batch resolves referenced_works (max 50 per filter call)
- citations(): resolves the citing works via cited_by_api_url
"""

import requests

from .base import CONTACT_EMAIL, DEFAULT_HEADERS, PaperHit, Source

API_URL = "https://api.openalex.org/works"

_SORT_MAP = {
    "relevance": None,  # search param already ranks by relevance
    "citations": "cited_by_count:desc",
    "date": "publication_date:desc",
}


def _reconstruct_abstract(inverted_index: dict | None) -> str:
    """OpenAlex stores abstracts as {word: [positions]}; rebuild the text."""
    if not inverted_index:
        return ""
    words = {}
    for word, positions in inverted_index.items():
        for pos in positions:
            words[pos] = word
    if not words:
        return ""
    return " ".join(words[i] for i in range(max(words) + 1) if i in words)


def _strip_doi_prefix(doi: str | None) -> str | None:
    if not doi:
        return None
    return doi.replace("https://doi.org/", "").replace("http://dx.doi.org/", "").strip()


class OpenAlexSource(Source):
    name = "openalex"
    display_name = "OpenAlex"
    description = "Open index of ~250M scholarly works (journals, preprints, books)"
    coverage = "Nature + all peer-reviewed journals, Crossref/PubMed/arXiv aggregation"
    requires_key = False
    rate_limit = "100k req/day polite pool (mailto tagged)"

    def _parse_work(self, work: dict) -> PaperHit:
        work_id = str(work.get("id", "")).rsplit("/", 1)[-1] or "unknown"
        doi = _strip_doi_prefix(work.get("doi"))

        venue = ""
        loc = work.get("primary_location") or {}
        source = loc.get("source") or {}
        if source.get("display_name"):
            venue = source["display_name"]

        authors = [a.get("author", {}).get("display_name", "")
                   for a in work.get("authorships", []) or []]
        authors = [a for a in authors if a]

        oa = work.get("open_access") or {}
        best_oa = work.get("best_oa_location") or {}
        pdf_url = best_oa.get("pdf_url") or oa.get("oa_url")

        landing = f"https://doi.org/{doi}" if doi else work.get("id", "")

        return PaperHit(
            source=self.name,
            id=f"openalex:{work_id}",
            title=work.get("display_name") or work_id,
            authors=authors,
            year=work.get("publication_year"),
            venue=venue,
            abstract=_reconstruct_abstract(work.get("abstract_inverted_index")),
            doi=doi,
            url=landing,
            pdf_url=pdf_url,
            citations_count=work.get("cited_by_count"),
            open_access=oa.get("is_oa"),
            retracted=work.get("is_retracted"),
            type=work.get("type") or "paper",
            extra={"openalex_id": work.get("id", "")},
        )

    def _get(self, url: str, params: dict) -> dict:
        params["mailto"] = CONTACT_EMAIL
        resp = requests.get(url, params=params, headers=DEFAULT_HEADERS, timeout=10)
        resp.raise_for_status()
        return resp.json()

    def search(self, query: str, limit: int = 10, year_from: int | None = None,
               year_to: int | None = None, sort: str = "relevance",
               open_access_only: bool = False) -> list[PaperHit]:
        params: dict = {"search": query, "per-page": max(1, min(limit, 200))}
        filters = []
        if year_from or year_to:
            filters.append(f"publication_year:{year_from or ''}-{year_to or ''}")
        if open_access_only:
            filters.append("open_access.is_oa:true")
        if filters:
            params["filter"] = ",".join(filters)
        if _SORT_MAP.get(sort):
            params["sort"] = _SORT_MAP[sort]

        data = self._get(API_URL, params)
        return [self._parse_work(w) for w in data.get("results", [])]

    def get(self, identifier: str, id_type: str = "auto") -> PaperHit | None:
        """identifier = OpenAlex work id (W...), optionally 'openalex:' prefixed."""
        work_id = identifier.strip()
        if work_id.startswith("openalex:"):
            work_id = work_id[len("openalex:"):]
        if "openalex.org/works/" in work_id:
            work_id = work_id.rsplit("/", 1)[-1]
        if not work_id.startswith("W"):
            return None
        data = self._get(f"{API_URL}/{work_id}", {})
        return self._parse_work(data)

    def _resolve_work(self, identifier: str, id_type: str = "auto") -> dict | None:
        """Resolve any supported identifier to the OpenAlex work dict."""
        ident = identifier.strip()
        if id_type in ("openalex", "auto") and (ident.startswith("W") or "openalex.org/works/" in ident):
            return self._get(f"{API_URL}/{ident.rsplit('/', 1)[-1].removeprefix('openalex:')}", {})
        filters = None
        if id_type == "doi":
            filters = f"doi:{ident}"
        elif id_type == "arxiv":
            filters = f"ids.arxiv:{ident}"
        elif id_type == "pmid":
            filters = f"pmid:{ident}"
        if not filters:
            return None
        data = self._get(API_URL, {"filter": filters, "per-page": 1})
        results = data.get("results", [])
        return results[0] if results else None

    def references(self, identifier: str, id_type: str = "auto", limit: int = 50) -> list[PaperHit]:
        work = self._resolve_work(identifier, id_type)
        if not work:
            return []
        ref_ids = work.get("referenced_works") or []
        if not ref_ids:
            return []
        # Batch-resolve via filter=ids.openalex:a|b|c (pipe-separated, <=50)
        for start in range(0, len(ref_ids), 50):
            chunk = ref_ids[start:start + 50]
            ids = "|".join(i.rsplit("/", 1)[-1] for i in chunk)
            try:
                data = self._get(API_URL, {"filter": f"ids.openalex:{ids}", "per-page": 50})
            except Exception:
                continue
            return [self._parse_work(w) for w in data.get("results", [])][:limit]
        return []

    def citations(self, identifier: str, id_type: str = "auto", limit: int = 50) -> list[PaperHit]:
        """Works that cite the given work. The legacy cited_by_api_url field was
        dropped from the API — the canonical filter is `cites:<openalex_id>`."""
        work = self._resolve_work(identifier, id_type)
        if not work:
            return []
        wid = work["id"].rsplit("/", 1)[-1]
        data = self._get(API_URL, {
            "filter": f"cites:{wid}",
            "per-page": min(limit, 100),
            "sort": "cited_by_count:desc",
        })
        return [self._parse_work(w) for w in data.get("results", [])][:limit]
