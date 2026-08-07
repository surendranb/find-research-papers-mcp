# SPDX-License-Identifier: Apache-2.0

"""PubMed source — NCBI E-utilities (esearch -> esummary + efetch). No key.

Covers MEDLINE/biomedical literature. efetch is used to pull abstracts
(esummary has none). PMCID presence marks free full text (pdf_url ->
PMC article). No public reference/citation graph via eutils.
"""

import re
import xml.etree.ElementTree as ET

import requests

from .base import DEFAULT_HEADERS, PaperHit, Source

ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
ESUMMARY = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
EFETCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"


def _year_from_pubdate(pubdate: str) -> int | None:
    m = re.match(r"^(\d{4})", pubdate or "")
    return int(m.group(1)) if m else None


class PubMedSource(Source):
    name = "pubmed"
    display_name = "PubMed"
    description = "MEDLINE biomedical literature (NCBI E-utilities)"
    coverage = "30M+ biomedical citations, free full-text links via PMC"
    requires_key = False
    rate_limit = "~3 req/s (NCBI polite pool, no key)"

    def _esummary(self, ids: list[str]) -> dict:
        resp = requests.get(ESUMMARY, params={
            "db": "pubmed", "id": ",".join(ids), "retmode": "json",
        }, headers=DEFAULT_HEADERS, timeout=25)
        resp.raise_for_status()
        return resp.json().get("result", {})

    def _efetch_abstracts(self, ids: list[str]) -> dict[str, str]:
        """PubMed abstracts come from efetch XML (esummary omits them)."""
        if not ids:
            return {}
        try:
            resp = requests.get(EFETCH, params={
                "db": "pubmed", "id": ",".join(ids), "retmode": "xml",
            }, headers=DEFAULT_HEADERS, timeout=30)
            resp.raise_for_status()
        except requests.RequestException:
            return {}
        out: dict[str, str] = {}
        try:
            root = ET.fromstring(resp.content)
        except ET.ParseError:
            return out
        for article in root.iter("PubmedArticle"):
            pmid_el = article.find(".//PMID")
            if pmid_el is None or not pmid_el.text:
                continue
            parts = []
            for at in article.iter("AbstractText"):
                label = at.get("Label")
                text = "".join(at.itertext()).strip()
                if text:
                    parts.append(f"{label}: {text}" if label else text)
            if parts:
                out[pmid_el.text] = re.sub(r"\s+", " ", " ".join(parts)).strip()
        return out

    def _parse_summary(self, doc: dict, abstracts: dict[str, str]) -> PaperHit:
        pmid = str(doc.get("uid", ""))
        ids = {i.get("idtype", "").lower(): i.get("value")
               for i in doc.get("articleids", [])}
        doi = ids.get("doi")
        pmc = ids.get("pmc")
        authors = [a.get("name", "") for a in doc.get("authors", []) or []]
        authors = [a for a in authors if a]
        return PaperHit(
            source=self.name,
            id=pmid,
            title=doc.get("title") or pmid,
            authors=authors,
            year=_year_from_pubdate(str(doc.get("pubdate") or doc.get("epubdate") or "")),
            venue=doc.get("fulljournalname") or "",
            abstract=abstracts.get(pmid, ""),
            doi=doi,
            url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
            pdf_url=f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmc}/" if pmc else None,
            open_access=bool(pmc),
            type="journal-article",
            extra={"pmc": pmc},
        )

    def _search_ids(self, query: str, limit: int, year_from: int | None,
                    year_to: int | None, sort: str) -> list[str]:
        term = query
        if year_from or year_to:
            term = f"({query}) AND ({year_from or 1800}:{year_to or 9999}[dp])"
        params = {
            "db": "pubmed",
            "term": term,
            "retmax": max(1, min(limit, 100)),
            "retmode": "json",
            "sort": "pub date" if sort == "date" else "relevance",
        }
        resp = requests.get(ESEARCH, params=params, headers=DEFAULT_HEADERS, timeout=25)
        resp.raise_for_status()
        return resp.json().get("esearchresult", {}).get("idlist", [])

    def search(self, query: str, limit: int = 10, year_from: int | None = None,
               year_to: int | None = None, sort: str = "relevance",
               open_access_only: bool = False) -> list[PaperHit]:
        ids = self._search_ids(query, limit, year_from, year_to, sort)
        if not ids:
            return []
        result = self._esummary(ids)
        abstracts = self._efetch_abstracts(ids)
        hits = [self._parse_summary(result[i], abstracts)
                for i in ids if i in result]
        if open_access_only:
            hits = [h for h in hits if h.open_access]
        return hits

    def get(self, identifier: str, id_type: str = "auto") -> PaperHit | None:
        pmid = identifier.strip()
        if pmid.startswith("pmid:"):
            pmid = pmid[len("pmid:"):]
        if pmid.startswith("https://pubmed.ncbi.nlm.nih.gov/"):
            pmid = pmid.rsplit("/", 2)[-2] if pmid.endswith("/") else pmid.rsplit("/", 1)[-1]
        if not pmid.isdigit():
            return None
        result = self._esummary([pmid])
        doc = result.get(pmid)
        if not doc:
            return None
        abstracts = self._efetch_abstracts([pmid])
        return self._parse_summary(doc, abstracts)
