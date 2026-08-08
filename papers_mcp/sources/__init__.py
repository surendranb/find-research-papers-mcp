# SPDX-License-Identifier: Apache-2.0

"""Source registry: everything search_papers / get_paper can query."""

import re
from datetime import datetime, timezone
from functools import lru_cache

import requests

from .base import DEFAULT_HEADERS, PaperHit, Source, UnconfiguredError
from .arxiv import ArxivSource
from .crossref import CrossrefSource
from .openalex import OpenAlexSource
from .pubmed import PubMedSource
from .semanticscholar import SemanticScholarSource

SOURCES: dict[str, Source] = {
    s.name: s for s in (
        ArxivSource(),
        OpenAlexSource(),
        CrossrefSource(),
        SemanticScholarSource(),
        PubMedSource(),
    )
}

# id_type -> owning source for get_paper dispatch
ID_TYPE_SOURCE = {
    "doi": "crossref",
    "arxiv": "arxiv",
    "pmid": "pubmed",
    "openalex": "openalex",
    "s2": "semanticscholar",
}

_DOI_RE = re.compile(r"^10\.\d{4,9}/")
_ARXIV_NEW_RE = re.compile(r"^\d{4}\.\d{4,5}(?:v\d+)?$")
_ARXIV_OLD_RE = re.compile(r"^[a-z-]+(?:\.[a-z-]+)*/\d{7}(?:v\d+)?$")
_PMID_RE = re.compile(r"^\d{7,9}$")
_OPENALEX_ID_RE = re.compile(r"^W\d{8,12}$")
_S2_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
                         re.IGNORECASE)


def guess_id_type(identifier: str) -> str:
    """Best-effort type guess for get_paper's 'auto' id_type."""
    s = (identifier or "").strip()
    low = s.lower()
    if low.startswith(("https://doi.org/", "http://dx.doi.org/", "doi:")) or _DOI_RE.match(s):
        return "doi"
    if "arxiv.org/abs/" in low or "arxiv.org/pdf/" in low:
        return "arxiv"
    if low.startswith("openalex:") or "openalex.org/works/" in low or _OPENALEX_ID_RE.match(s):
        return "openalex"
    if low.startswith(("s2:", "semanticscholar:")) or "semanticscholar.org/paper/" in low \
            or _S2_UUID_RE.match(s):
        return "s2"
    if low.startswith("pmid:") or "pubmed.ncbi.nlm.nih.gov/" in low:
        return "pmid"
    if _ARXIV_NEW_RE.match(s) or _ARXIV_OLD_RE.match(s):
        return "arxiv"
    if _PMID_RE.match(s):
        return "pmid"
    return "doi"  # most common opaque identifier is a DOI


def get_source(name: str) -> Source | None:
    return SOURCES.get(name)


def list_sources() -> list[dict]:
    return [s.status() for s in SOURCES.values()]


@lru_cache(maxsize=512)
def _head_resolves(url: str) -> bool | None:
    """Liveness probe: does the landing page answer 2xx/3xx? True/False when
    the target answered, None when it was unreachable or blocks HEAD (so we
    never report a paper as dead on a network error)."""
    try:
        resp = requests.head(url, headers=DEFAULT_HEADERS, timeout=8,
                             allow_redirects=True)
        if resp.status_code in (404, 410):
            return False
        if 200 <= resp.status_code < 500:
            return True
        return None
    except Exception:
        return None


def verify_paper(paper: PaperHit) -> dict:
    """3-layer verification for a resolved paper: liveness (landing page
    answers), integrity (OpenAlex retraction flag when the owner source does
    not track it). Never hard-fails a paper — resolves=None means 'unknown'."""
    url = None
    if paper.doi:
        url = f"https://doi.org/{paper.doi}"
    elif paper.source == "arxiv" and paper.id:
        url = f"https://arxiv.org/abs/{paper.id}"
    elif paper.source == "pubmed" and paper.id:
        url = f"https://pubmed.ncbi.nlm.nih.gov/{paper.id}"

    resolves, error = None, None
    if url:
        resolves = _head_resolves(url)
        if resolves is None:
            error = "landing page did not answer HEAD (offline or bot-blocked); status unknown"

    retracted = paper.retracted
    if retracted is None and paper.doi:
        try:
            work = SOURCES["openalex"]._resolve_work(paper.doi, "doi")
            retracted = bool(work.get("is_retracted")) if work else None
        except Exception:
            pass
    if paper.retracted is None and retracted is not None:
        paper.retracted = retracted

    verification = {
        "resolves": resolves,
        "retracted": retracted,
        "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    if error:
        verification["error"] = error
    return verification


def search_all(query: str, sources: list[str] | None = None, limit: int = 10,
               year_from: int | None = None, year_to: int | None = None,
               sort: str = "relevance", open_access_only: bool = False) -> dict:
    """Aggregate search. Returns {hits: [...], skipped: [...]} — skipped lists
    sources that failed or are unconfigured, so callers can explain."""
    names = sources or list(SOURCES.keys())
    unknown = [n for n in names if n not in SOURCES]
    if unknown:
        raise ValueError(
            f"unknown source(s): {', '.join(unknown)}. Known: {', '.join(SOURCES)}")

    hits: list[PaperHit] = []
    skipped: list[dict] = []
    queried: list[str] = []
    per_source_limit = max(limit, 1)
    for name in names:
        src = SOURCES[name]
        if not src.configured():
            skipped.append({"source": name, "reason": "key_required",
                            "hint": src.key_hint})
            continue
        queried.append(name)
        try:
            hits.extend(src.search(query, per_source_limit, year_from, year_to,
                                   sort, open_access_only))
        except UnconfiguredError as e:
            skipped.append({"source": name, "reason": "key_required", "hint": str(e)})
        except Exception as e:
            skipped.append({"source": name, "reason": "error", "detail": str(e)[:200]})

    # Round-robin across sources so one prolific source (e.g. arXiv on CS
    # topics) cannot monopolize a small result window — cross-source discovery
    # is the point of a multi-source search.
    per_source = {}
    for hit in hits:
        per_source.setdefault(hit.source, []).append(hit)
    interleaved = []
    buckets = list(per_source.values())
    while buckets:
        nxt = []
        for bucket in buckets:
            if bucket:
                interleaved.append(bucket.pop(0))
                nxt.append(bucket)
        buckets = nxt
    return {
        "hits": [h.to_dict() for h in interleaved[:limit]],
        "skipped": skipped,
        "sources_queried": queried,
    }


def get_paper(identifier: str, id_type: str = "auto",
              include_references: bool = True,
              include_citations: bool = True,
              verify: bool = True) -> dict:
    """Resolve one paper + its references/citations across sources.

    References/citations come from the owning source when available (Crossref
    for DOIs, OpenAlex/S2 for their ids); citations additionally fall back to
    OpenAlex so arXiv/DOI/PMID identifiers still get a citing-works list.

    verify=True (default) adds a verification block: liveness HEAD-check of
    the landing page plus OpenAlex retraction flag when the owner does not
    track it. A dead/unknown target never fails the paper — it is reported.
    """
    resolved_type = guess_id_type(identifier) if id_type == "auto" else id_type
    if resolved_type not in ID_TYPE_SOURCE:
        return {"error": f"unknown id_type '{resolved_type}'. "
                         f"Use one of: {', '.join(ID_TYPE_SOURCE)}"}

    owner = SOURCES[ID_TYPE_SOURCE[resolved_type]]
    paper = owner.get(identifier, resolved_type)
    if paper is None:
        return {
            "error": f"paper not found via {owner.display_name} "
                     f"(id_type={resolved_type}, identifier={identifier})",
            "id_type": resolved_type,
        }

    references: list[PaperHit] = []
    citations: list[PaperHit] = []
    notes: list[str] = []

    if include_references:
        try:
            references = owner.references(identifier, resolved_type) or []
        except Exception as e:
            notes.append(f"references unavailable: {str(e)[:120]}")

    if include_citations:
        try:
            citations = owner.citations(identifier, resolved_type) or []
        except Exception as e:
            notes.append(f"citations unavailable: {str(e)[:120]}")
        if not citations and owner.name != "openalex":
            # Uniform citations fallback: OpenAlex indexes citing works for
            # DOI / arXiv / PMID identifiers.
            try:
                citations = SOURCES["openalex"].citations(identifier, resolved_type) or []
            except Exception:
                pass

    if not references and owner.name in ("arxiv", "pubmed"):
        notes.append(f"{owner.display_name} does not expose a public reference list")
    if not citations and owner.name != "openalex":
        notes.append("citing works not available from this source (OpenAlex fallback "
                     "applies when the work is indexed there)")

    verification = verify_paper(paper) if verify else None
    response = {
        "paper": paper.to_dict(),
        "references": [r.to_dict() for r in references],
        "citations": [c.to_dict() for c in citations],
        "id_type": resolved_type,
        "notes": notes,
    }
    if verification is not None:
        response["verification"] = verification
    return response
