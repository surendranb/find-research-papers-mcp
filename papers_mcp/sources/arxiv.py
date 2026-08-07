# SPDX-License-Identifier: Apache-2.0

"""arXiv source — export.arxiv.org Atom API. No key required.

Covers CS, physics, math, q-bio, q-fin, statistics, and eess preprints.
No public reference/citation graph (arXiv does not expose one) — get() is
supported, references()/citations() return empty lists.
"""

import re
import xml.etree.ElementTree as ET

import requests

from .base import DEFAULT_HEADERS, PaperHit, Source

ATOM_NS = "http://www.w3.org/2005/Atom"
ARXIV_NS = "http://arxiv.org/schemas/atom"
API_URL = "https://export.arxiv.org/api/query"  # HTTPS — plain HTTP returns empty

_SORT_MAP = {
    "relevance": "relevance",
    "citations": "submittedDate",  # arXiv has no citation sort; newest-first is the proxy
    "date": "submittedDate",
}

_ARXIV_ID_RE = re.compile(r"^(\d{4}\.\d{4,5}(?:v\d+)?|[a-z-]+(?:\.[a-z-]+)*/\d{7}(?:v\d+)?)$")


def _norm_text(value: str) -> str:
    """arXiv XML wraps titles/abstracts in whitespace + newlines."""
    return re.sub(r"\s+", " ", (value or "")).strip()


class ArxivSource(Source):
    name = "arxiv"
    display_name = "arXiv"
    description = "Open-access preprint server (CS, physics, math, biology, stats)"
    coverage = "CS, physics, math, q-bio, q-fin, statistics, eess preprints"
    requires_key = False
    rate_limit = "~1 req/3s (polite; no key)"

    def _parse_entry(self, entry: ET.Element) -> PaperHit:
        def _find(tag: str, ns: str = ATOM_NS) -> str:
            el = entry.find(f"{{{ns}}}{tag}")
            return _norm_text(el.text) if el is not None and el.text else ""

        arxiv_id = _find("id").rsplit("/abs/", 1)[-1].strip()
        title = _find("title")
        abstract = _find("summary")

        authors = [a.findtext(f"{{{ATOM_NS}}}name", default="").strip()
                   for a in entry.findall(f"{{{ATOM_NS}}}author")]
        authors = [a for a in authors if a]

        year = None
        published = _find("published")
        m = re.match(r"^(\d{4})", published)
        if m:
            year = int(m.group(1))

        categories = [c.get("term", "") for c in entry.findall(f"{{{ARXIV_NS}}}category")]
        doi_el = entry.find(f"{{{ARXIV_NS}}}doi")
        doi = _norm_text(doi_el.text) if doi_el is not None and doi_el.text else None

        url = f"https://arxiv.org/abs/{arxiv_id}"
        pdf_url = f"https://arxiv.org/pdf/{arxiv_id}"

        return PaperHit(
            source=self.name,
            id=arxiv_id,
            title=title or arxiv_id,
            authors=authors,
            year=year,
            venue="arXiv",
            abstract=abstract,
            doi=doi,
            url=url,
            pdf_url=pdf_url,
            open_access=True,  # arXiv preprints are open access by definition
            type="preprint",
            extra={"categories": categories},
        )

    def search(self, query: str, limit: int = 10, year_from: int | None = None,
               year_to: int | None = None, sort: str = "relevance",
               open_access_only: bool = False) -> list[PaperHit]:
        params = {
            "search_query": f'all:"{query}"',
            "start": 0,
            "max_results": limit,
            "sortBy": _SORT_MAP.get(sort, "relevance"),
            "sortOrder": "descending",
        }
        resp = requests.get(API_URL, params=params, headers=DEFAULT_HEADERS, timeout=25)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)

        hits: list[PaperHit] = []
        for entry in root.findall(f"{{{ATOM_NS}}}entry"):
            hit = self._parse_entry(entry)
            if year_from and hit.year and hit.year < year_from:
                continue
            if year_to and hit.year and hit.year > year_to:
                continue
            hits.append(hit)
        return hits

    def get(self, identifier: str, id_type: str = "auto") -> PaperHit | None:
        arxiv_id = identifier.strip()
        if "arxiv.org/" in arxiv_id:
            arxiv_id = arxiv_id.rsplit("/", 1)[-1].replace("v", "v", 1)
        if arxiv_id.endswith(".pdf"):
            arxiv_id = arxiv_id[:-4]
        if not _ARXIV_ID_RE.match(arxiv_id):
            return None
        params = {"id_list": arxiv_id, "max_results": 1}
        resp = requests.get(API_URL, params=params, headers=DEFAULT_HEADERS, timeout=25)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        entries = root.findall(f"{{{ATOM_NS}}}entry")
        return self._parse_entry(entries[0]) if entries else None
