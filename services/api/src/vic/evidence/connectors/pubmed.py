"""PubMed connector (NCBI E-utilities: esearch + efetch).

Gives ABSTRACTS only (no full text); this is stated in every evidence's limitations.
Literature evidence is scoped as `approach`: an abstract is never credited to a specific
program automatically.
Limits (NCBI docs): 3 requests/s without API key, 10/s with one; `tool`/`email` recommended.
Env: NCBI_API_KEY (optional), NCBI_EMAIL (recommended).
"""
from __future__ import annotations

import asyncio
import calendar
import os
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import date

import httpx

from vic.contracts import Scope

from ..importer import ParsedDocument
from .base import (
    ConnectorResult,
    RateLimiter,
    Sleep,
    SourceUnavailable,
    get_with_retries,
    make_record_document,
)

ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
EFETCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}


@dataclass
class PubMedRecord:
    pmid: str
    title: str
    abstract: list[tuple[str | None, str]]
    pub_date: date | None
    date_imprecise: bool
    pub_types: list[str] = field(default_factory=list)
    mesh: list[str] = field(default_factory=list)


def build_queries(mechanism: str, indication: str) -> dict[str, str]:
    """Efficacy, safety and NEGATIVE-result queries: we search against our own hypothesis too."""
    m = mechanism.replace('"', " ").strip()
    i = indication.replace('"', " ").strip()
    return {
        "efficacy": f'("{m}") AND ("{i}")',
        "safety": f'("{m}") AND (safety OR toxicity OR "adverse events" OR hepatotoxicity)',
        "negative": f'("{m}") AND ("{i}") AND (failed OR failure OR "lack of efficacy" '
                    f'OR terminated OR discontinued OR "no significant")',
    }


# ---------------------------------------------------------------- XML parsing

def _text(el: ET.Element | None) -> str:
    return " ".join("".join(el.itertext()).split()) if el is not None else ""


def _int(value: str | None) -> int | None:
    return int(value) if value and value.strip().isdigit() else None


def _date_from(el: ET.Element) -> tuple[date | None, bool]:
    """Missing parts are filled with the LATEST possible value (conservative for leakage)."""
    year = _int(el.findtext("Year"))
    if year is None:
        m = re.search(r"(\d{4})", el.findtext("MedlineDate") or "")
        return (date(int(m.group(1)), 12, 31), True) if m else (None, False)
    raw_month = (el.findtext("Month") or "").strip()
    month = _int(raw_month) or _MONTHS.get(raw_month[:3].lower())
    day = _int(el.findtext("Day"))
    try:
        if month is None:
            return date(year, 12, 31), True
        if day is None:
            return date(year, month, calendar.monthrange(year, month)[1]), True
        return date(year, month, day), False
    except ValueError:
        return None, False


def _pub_date(article: ET.Element) -> tuple[date | None, bool]:
    for path in ("ArticleDate", "Journal/JournalIssue/PubDate"):
        el = article.find(path)
        if el is not None:
            d, imprecise = _date_from(el)
            if d:
                return d, imprecise
    return None, False


def parse_pubmed_xml(xml_text: str) -> list[PubMedRecord]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise SourceUnavailable("PubMed", "response was not valid XML") from exc
    out: list[PubMedRecord] = []
    for art in root.iter("PubmedArticle"):
        cit = art.find("MedlineCitation")
        article = cit.find("Article") if cit is not None else None
        pmid = _text(cit.find("PMID")) if cit is not None else ""
        if article is None or not pmid:
            continue
        abstract = []
        for at in article.findall("Abstract/AbstractText"):
            t = _text(at)
            if t:
                abstract.append((at.get("Label"), t))
        pub_date, imprecise = _pub_date(article)
        out.append(
            PubMedRecord(
                pmid=pmid,
                title=_text(article.find("ArticleTitle")),
                abstract=abstract,
                pub_date=pub_date,
                date_imprecise=imprecise,
                pub_types=[_text(x) for x in article.findall("PublicationTypeList/PublicationType")],
                mesh=[_text(x) for x in cit.findall("MeshHeadingList/MeshHeading/DescriptorName")],
            )
        )
    return out


def _limitations(rec: PubMedRecord, kinds: list[str]) -> list[str]:
    lims = ["Abstract only; full text was not retrieved."]
    mesh = {m.lower() for m in rec.mesh}
    animal = mesh & {"animals", "mice", "rats", "disease models, animal"}
    if animal and "humans" not in mesh:
        lims.append("MeSH indexing suggests non-human (animal) data; not evidence of human efficacy/safety.")
    elif "humans" in mesh and not animal:
        lims.append("MeSH indexing: human study (verify population in the abstract).")
    if any("retract" in t.lower() for t in rec.pub_types):
        lims.append("Publication type indicates a retraction or retracted publication.")
    if rec.date_imprecise:
        lims.append("Publication date is imprecise (year/month only); latest possible date is used.")
    lims.append("Found via PubMed query: " + ", ".join(kinds) + ".")
    return lims


# ---------------------------------------------------------------- connector

class PubMedConnector:
    name = "PubMed"

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        api_key: str | None = None,
        email: str | None = None,
        tool: str = "vic-evidence",
        retmax: int = 5,
        sleep: Sleep = asyncio.sleep,
        min_interval: float | None = None,
        max_attempts: int = 3,
        backoff: float = 1.0,
    ) -> None:
        self.client = client
        self.api_key, self.email, self.tool = api_key, email, tool
        self.retmax = retmax
        self._sleep, self._max_attempts, self._backoff = sleep, max_attempts, backoff
        if min_interval is None:
            min_interval = 0.11 if api_key else 0.34  # 10/s with key, 3/s without
        self.limiter = RateLimiter(min_interval, sleep=sleep)

    @classmethod
    def from_env(cls, client: httpx.AsyncClient, **kw) -> "PubMedConnector":
        return cls(client, api_key=os.getenv("NCBI_API_KEY") or None, email=os.getenv("NCBI_EMAIL") or None, **kw)

    def _params(self, **extra) -> dict:
        p = {"tool": self.tool, **extra}
        if self.email:
            p["email"] = self.email
        if self.api_key:
            p["api_key"] = self.api_key
        return p

    async def _get(self, url: str, params: dict) -> httpx.Response:
        return await get_with_retries(
            self.client, url, params=params, source=self.name, limiter=self.limiter,
            max_attempts=self._max_attempts, backoff=self._backoff, sleep=self._sleep,
        )

    async def _esearch(self, term: str, as_of: date | None) -> list[str]:
        extra = {"db": "pubmed", "term": term, "retmax": self.retmax, "retmode": "json", "sort": "relevance"}
        if as_of:
            extra.update(datetype="edat", mindate="1800/01/01", maxdate=as_of.strftime("%Y/%m/%d"))
        resp = await self._get(ESEARCH, self._params(**extra))
        try:
            data = resp.json()["esearchresult"]
        except (ValueError, KeyError, TypeError) as exc:
            raise SourceUnavailable(self.name, "unexpected search response format") from exc
        if "ERROR" in data or "error" in data:
            raise SourceUnavailable(self.name, "search was rejected by the service")
        return [str(i) for i in data.get("idlist", [])]

    async def _efetch(self, pmids: list[str]) -> str:
        resp = await self._get(
            EFETCH, self._params(db="pubmed", id=",".join(pmids), retmode="xml")
        )
        return resp.text

    async def search(self, queries: dict[str, str], *, as_of: date | None = None) -> ConnectorResult:
        res = ConnectorResult(source=self.name)
        kinds: dict[str, list[str]] = {}
        failed = 0
        for kind, term in queries.items():
            try:
                ids = await self._esearch(term, as_of)
            except SourceUnavailable as exc:
                failed += 1
                res.warnings.append(
                    f"PubMed [{kind}]: source did not respond ({exc.detail}). This is NOT evidence "
                    "of absence (including absence of safety signals); retry or check manually."
                )
                continue
            if not ids:
                res.warnings.append(f"PubMed [{kind}]: the search succeeded but returned no records.")
            for pmid in ids:
                kinds.setdefault(pmid, []).append(kind)

        if not kinds:
            res.status = "unavailable" if failed == len(queries) else "empty"
            return res
        try:
            records = parse_pubmed_xml(await self._efetch(list(kinds)))
        except SourceUnavailable as exc:
            res.status = "unavailable"
            res.warnings.append(
                f"PubMed: found {len(kinds)} record IDs but could not download them ({exc.detail}). "
                "No evidence from PubMed is included; this is NOT evidence of absence."
            )
            return res

        if as_of:
            res.warnings.append(
                f"PubMed: as_of_date {as_of.isoformat()} applied via Entrez date and publication date. "
                "Abstracts may have been revised after that date; strict historical evaluation "
                "needs a frozen snapshot."
            )
        for rec in records:
            label = f"PubMed PMID {rec.pmid}"
            if not rec.abstract:
                res.warnings.append(f"{label}: no abstract available; skipped (nothing invented).")
                continue
            if as_of and (rec.pub_date is None or rec.pub_date > as_of):
                res.warnings.append(
                    f"{label}: excluded by as_of_date (publication date "
                    f"{rec.pub_date.isoformat() if rec.pub_date else 'unknown'})."
                )
                continue
            body = "\n\n".join(f"{lab}: {t}" if lab else t for lab, t in rec.abstract)
            res.documents.append(
                make_record_document(
                    rec.title or f"PubMed record {rec.pmid}",
                    [("Abstract", body)],
                    source_type="preprint" if any(t.lower() == "preprint" for t in rec.pub_types) else "peer_reviewed",
                    url=f"https://pubmed.ncbi.nlm.nih.gov/{rec.pmid}/",
                    identifier=f"PMID{rec.pmid}",
                    published_at=rec.pub_date,
                    scope=Scope.APPROACH,
                    limitations=_limitations(rec, kinds.get(rec.pmid, [])),
                )
            )
        res.status = "empty" if not res.documents else ("partial" if failed else "ok")
        return res


async def _demo(mechanism: str, indication: str) -> None:
    async with httpx.AsyncClient() as client:
        res = await PubMedConnector.from_env(client).search(build_queries(mechanism, indication))
    print("status:", res.status)
    for w in res.warnings:
        print("WARN:", w)
    for d in res.documents:
        print(d.identifier, d.published_at, d.source_type, "|", d.title[:90])


if __name__ == "__main__":
    import sys

    asyncio.run(_demo(sys.argv[1], sys.argv[2]))
    