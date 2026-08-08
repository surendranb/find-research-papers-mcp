# Scholarly API Capabilities Deep Dive — with/without creds, features we enable

Date: 2026-08-08. Method: every claim below was live-probed (HTTP requests)
this day unless labeled otherwise. Probes: arXiv, OpenAlex, Crossref,
Semantic Scholar, PubMed, Europe PMC, DOAJ, ChinaXiv, CNKI/Wanfang/CQVIP.

## 1. Current sources — verified capabilities

### arXiv (export.arxiv.org) — no creds, ever
- Date-range query `submittedDate:[20250101 TO 20250601]` ✅ (2 entries)
- Sort `sortBy=submittedDate|relevance|lastUpdatedDate` ✅
- Fetch by ID `id_list=` ✅
- Queries: `all:`/`abs:`/`title:`/`cat:`/`au:` prefixes, boolean AND/OR/ANDNOT
- Rate: ~1 req/3s (documented; probe slept 3.1s between calls)

### OpenAlex (api.openalex.org) — no key, polite pool via `mailto=`
- `search=` + `filter=publication_year:2025` + `sort=cited_by_count:desc` ✅
  (1434 hits for "streak motivation", 2025)
- `filter=cites:W...` (works citing a work) ✅ (1238 citing works)
- `abstract_inverted_index` reconstructable ✅ (134 keys on a Nature paper)
- Other filters: `from_publication_date`, `doi:`, `pmid:`, `arxiv:`,
  `open_access.is_oa`, `type:`, `primary_location.source.id`
- Sorts: `relevance_score`, `cited_by_count`, `publication_date`
- Scope: ~323M works, 2B+ citation links, 60M fulltext PDFs,
  `best_oa_location` (paywall-proof PDF link)
- Rate: 100k req/day polite pool (10 rps) with mailto; ~10 rps without
- Adapter uses `CONTACT_EMAIL = "reachsuren@gmail.com"` (sources/base.py:16)

### Crossref (api.crossref.org) — no key, polite pool via `mailto=`
- `query.bibliographic=` + `filter=from-pub-date,until-pub-date` +
  `sort=is-referenced-by-count` ✅ (top hit cited 1210x)
- Reference list on a paywalled Nature paper ✅ (57 refs) — the
  paywall-proofing feature: full citation graph without access
- Query params: `query.title`, `query.author`, `query.container-title`;
  filters: `type:`, `has-license`; sorts: `published`, `score`
- Abstracts: partial (~20% of records, JATS-wrapped; adapter strips JATS)
- Quirk (known): single-work route rejects `select` — use `rows=1`

### Semantic Scholar (graph/v1) — without key: unreliable
- **Without key: HTTP 429 today** (shared unauthenticated pool exhausted) —
  this is why `semanticscholar.py` carries a polite rate limiter + 429 retry
- With free API key: 100 req/5min (shared pool, ~1 rps without key)
- Features with key: `sort=citationCount:desc`, `year=2024-2026`,
  `fieldsOfStudy`, `openAccessPdf`, `tldr`, `references`/`citations`
  endpoints, `externalIds` (DOI/PMID/arXiv/PMC crosswalk)

### PubMed (eutils.ncbi.nlm.nih.gov) — no key (key = 10 rps vs 3 rps)
- Term date-range `(2024:2026[dp])` + `sort=pubdate` ✅ (3 IDs returned)
- `esummary` articleids → DOI + PMC ID crosswalk ✅ (PMC13445181)
- Filters via term: `review[pt]`, `free full text[filter]`,
  `open access[filter]`, `humans[mesh]`, language
- `efetch` → full abstract text
- Free NCBI API key raises 3 → 10 req/s (optional env var)

## 2. Extension candidates — verified

### Europe PMC (europepmc.org) — no key ✅
- Search ✅ (hitCount 753 for "streak AND habit"), `sort=CITED desc` ✅
- `resultType=core` → abstract ✅ + `fullTextUrlList` ✅ + PMID/PMC
- Superset of PubMed + full text + ORCID links. **Cheapest coverage win.**

### DOAJ (api.doaj.org) — no key ✅
- Public API alive (200); global open-access journals (incl. Chinese OA
  journals); filters for license, subject, publisher country

### ChinaXiv (chinaxiv.org, CAS preprint platform) — geo-blocked
- ~45.5k Chinese-language preprints, DOIs `10.12074/…`, CC-licensed
- OAI-PMH endpoint (`/oai/`) live-tested: HTTP 200 but body
  "Sorry! You have no right to access this web." — IP-gated
- Web search endpoint: HTTP 403 (outside China)
- DOAPR registry lists it as "metadata openly available via API" — that is
  true only from Chinese IPs. Not usable from this host today.

### CNKI / Wanfang / CQVIP (the "Big Three") — closed or commercial
- CNKI (largest): "知网研学" open platform exists but requires developer
  account → app creation → **manual approval of interface permissions** +
  JWT (AppId/ApiKey/SecretKey). Institutional/commercial, not open.
- Wanfang: `apps.wanfangdata.com.cn/open/` — 会员制按量付费 (membership,
  pay-per-use API sales). Commercial.
- CQVIP (~15k journals): `api.cqvip.com` exists; subscription business,
  no public access tier documented.
- Verdict: accessing any of these without institutional credentials means
  scraping — which violates the studio opinion law ("if a platform offers an
  API, use it; never skirt rules"). Out of Phase 1 by principle, not oversight.

## 3. The Asia/China coverage question — evidence

What is covered today (all key-free via our 5 sources):
- Chinese-authored papers published in international journals (the bulk of
  what global researchers cite) — OpenAlex/Crossref/S2/PubMed index these
  fully; no gap for this population.
- Chinese-language journals with DOIs — Crossref carries these: ISTIC&Wanfang
  and CNKI are two of the world's 12 DOI registration agencies and register
  DOIs for Chinese-language journals (Scientometrics 2026).

What is NOT covered (the real gap): Chinese-language-only domestic journal
literature.
- OpenAlex: only **37% of GCJC core Chinese journals, 24% of their articles**
  (arXiv:2512.16339, Dec 2025; Scientometrics 10.1007/s11192-026-05664-4).
  91% of covered journals have <50% article coverage. Metadata weak:
  missing affiliations/references, Chinese articles mislabeled English,
  irregular pinyin titles, sparse DOIs.
- OpenAlex CNKI-sourced coverage **collapsed to ~zero by 2016** (CNKI blocked
  overseas crawling; Zheng et al., JASIST 2025). What little Chinese-journal
  data OpenAlex has (~2/3) came via CNKI — hence the instability.
- ChinaXiv geo-blocked (verified today). NCPSSD (26M articles), KCI (Korea),
  CiNii/J-STAGE (Japan, registration+token) — closed or gated.

Regional parallels that ARE open: SciELO/Redalyc (LatAm, no key) — pattern
proves regional coverage is doable via open repositories, not via the Big Three.

## 4. Features we enable — instruction → verified capability

| Instruction | Capability (all verified above) |
|---|---|
| "latest papers on X" | arXiv `sortBy=submittedDate`; PubMed `sort=pubdate`; OpenAlex `sort=publication_date:desc` |
| "papers from 2025" | date-range on arXiv/OpenAlex/Crossref/PubMed (S2 `year=`) |
| "most cited on X" | OpenAlex `sort=cited_by_count:desc`; Crossref `sort=is-referenced-by-count` |
| "references of X" | Crossref `reference` (works on paywalled papers — 57 refs verified); OpenAlex `referenced_works` |
| "works citing X" | OpenAlex `filter=cites:` (1238 verified); S2 `/citations` (needs key) |
| "open access only" | OpenAlex `open_access.is_oa` + `best_oa_location` PDF; PubMed `free full text[filter]` |
| "abstract of X" | OpenAlex inverted-index reconstruction; PubMed efetch; Crossref partial (JATS-stripped) |
| "find by DOI/PMID/arXiv id" | `guess_id_type` dispatch in `__init__.py` |

## 5. Decisions

**Principle (thesis #9, studio law):** no workarounds — we only make easier
what a person can access normally. No scraping, no VPN-ing, no skirting
paywalls. Every result comes from an official API a human could hit directly.

1. **Phase 1: ship with the 5 current sources; document the China gap
   honestly** in list_sources output + README. The "verified papers"
   positioning gets *stronger* from naming the boundary than from pretending
   universality.
2. **Phase 1.5 (do next): add Europe PMC** — no key, superset of PubMed,
   full text + abstracts verified. Biggest coverage-per-effort add.
3. **Phase 2 candidates:** DOAJ (no key) + BASE/CORE (free key) for global
   OA aggregation; revisit ChinaXiv only if reachable (geo-block is on the
   provider side; a mirror/API may appear — watch `experimental-ext-skills`-style
   status changes, do not proxy).
4. **Never:** scrape CNKI/Wanfang/CQVIP. If a paid tier is wanted later, it
   goes through their official (paid) APIs as a separate creds-gated source.
5. **Semantic Scholar:** keep 429 retry; add optional `S2_API_KEY` env var
   (free key) to unlock citations/references reliably.
