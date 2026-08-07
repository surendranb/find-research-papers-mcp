# SPDX-License-Identifier: Apache-2.0

"""Source abstraction: every scholarly source implements search() (and
optionally get()/references()/citations()) and returns PaperHit rows with a
unified schema."""

from dataclasses import dataclass, asdict, field

# Descriptive UA: arXiv/OpenAlex/Crossref and some peers reject default
# library UAs (403/empty responses).
DEFAULT_HEADERS = {
    "User-Agent": "papers-mcp/0.1.0 (MCP server; contact: reachsuren@gmail.com)"
}

# Polite-pool contact for APIs that reward it (OpenAlex).
CONTACT_EMAIL = "reachsuren@gmail.com"


class UnconfiguredError(Exception):
    """Raised by a live source whose API key is not set."""


class UnavailableError(Exception):
    """Raised when a source is reachable but refuses service (e.g. 429 rate
    limit on a shared pool without a key). Callers skip it gracefully."""


@dataclass
class PaperHit:
    """Unified scholarly result row across all sources.

    Guaranteed non-empty: source, id, title, url. Everything else is best-effort.
    """

    source: str
    id: str  # source-specific: arXiv id / DOI / PMID / OpenAlex id / S2 paperId
    title: str
    authors: list = field(default_factory=list)
    year: int | None = None
    venue: str = ""  # journal / conference / repository name
    abstract: str = ""
    doi: str | None = None
    url: str = ""  # landing page
    pdf_url: str | None = None  # open-access PDF when available
    citations_count: int | None = None
    open_access: bool | None = None
    type: str = "paper"  # paper, preprint, review, journal-article, ...
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


class Source:
    """Base class. Subclasses set the class attributes and implement search().

    get()/references()/citations() return None/[] when the source does not
    expose that capability (arXiv and PubMed have no public citation graph).
    """

    name: str = ""
    display_name: str = ""
    description: str = ""
    coverage: str = ""  # what the source indexes
    requires_key: bool = False
    key_hint: str = ""  # env var name when requires_key
    rate_limit: str = ""  # human summary

    def configured(self) -> bool:
        return True

    def search(self, query: str, limit: int = 10, year_from: int | None = None,
               year_to: int | None = None, sort: str = "relevance",
               open_access_only: bool = False) -> list[PaperHit]:
        raise NotImplementedError

    def get(self, identifier: str, id_type: str = "auto") -> PaperHit | None:
        """Resolve one paper by this source's own identifier."""
        return None

    def references(self, identifier: str, id_type: str = "auto",
                   limit: int = 50) -> list[PaperHit]:
        """Papers cited BY the given paper. Empty when unsupported."""
        return []

    def citations(self, identifier: str, id_type: str = "auto",
                  limit: int = 50) -> list[PaperHit]:
        """Papers citing the given paper. Empty when unsupported."""
        return []

    def status(self) -> dict:
        return {
            "name": self.name,
            "display_name": self.display_name,
            "description": self.description,
            "coverage": self.coverage,
            "rate_limit": self.rate_limit,
            "requires_key": self.requires_key,
            "key_hint": self.key_hint if (self.requires_key and not self.configured()) else None,
            "configured": self.configured(),
        }
