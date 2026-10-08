"""ClinicalTrials.gov API v2 connector.

Three queries: the intervention itself, STOPPED trials (terminated/withdrawn/suspended) and
competitor trials for the same condition. Registry records describe a trial, not its results,
so evidence is scoped `approach` and every record carries that limitation.
Rate limit (~50 requests/min per IP, verify at clinicaltrials.gov/data-api): 1.3 s between calls.
No credentials needed.
"""
from __future__ import annotations

import asyncio
import calendar
import re
from dataclasses import dataclass, field
from datetime import date

import httpx

from vic.contracts import Scope

from .base import (
    ConnectorResult,
    RateLimiter,
    Sleep,
    SourceUnavailable,
    get_with_retries,
    make_record_document,
)

STUDIES = "https://clinicaltrials.gov/api/v2/studies"
STOPPED = "TERMINATED,WITHDRAWN,SUSPENDED"
COMPETITOR_STATUSES = "RECRUITING,ACTIVE_NOT_RECRUITING,COMPLETED"


@dataclass
class CtRecord:
    nct: str
    title: str
    status: str
    why_stopped: str | None
    phases: list[str]
    study_type: str | None
    conditions: list[str]
    interventions: list[str]
    sponsor: str | None
    summary: str | None
    first_posted: date | None
    first_posted_raw: str | None
    date_imprecise: bool
    start: str | None
    last_update: str | None
    has_results: bool = False
    kinds: list[str] = field(default_factory=list)


def _ct_date(raw: str | None) -> tuple[date | None, bool]:
    """'2022-03' -> 2022-03-31 (latest possible, imprecise); '2022' -> 2022-12-31."""
    m = re.fullmatch(r"(\d{4})(?:-(\d{2}))?(?:-(\d{2}))?", (raw or "").strip())
    if not m:
        return None, False
    y, mo, d = int(m[1]), m[2], m[3]
    try:
        if mo is None:
            return date(y, 12, 31), True
        if d is None:
            return date(y, int(mo), calendar.monthrange(y, int(mo))[1]), True
        return date(y, int(mo), int(d)), False
    except ValueError:
        return None, False


def parse_study(study: dict) -> CtRecord | None:
    p = study.get("protocolSection") or {}
    ident = p.get("identificationModule") or {}
    nct = ident.get("nctId")
    if not nct:
        return None
    status = p.get("statusModule") or {}
    first_raw = (
        status.get("studyFirstPostDateStruct") or status.get("firstPostDateStruct") or {}
    ).get("date")    
    first, imprecise = _ct_date(first_raw)
    return CtRecord(
        nct=nct,
        title=ident.get("briefTitle") or ident.get("officialTitle") or nct,
        status=status.get("overallStatus") or "UNKNOWN",
        why_stopped=status.get("whyStopped"),
        phases=list((p.get("designModule") or {}).get("phases") or []),
        study_type=(p.get("designModule") or {}).get("studyType"),
        conditions=list((p.get("conditionsModule") or {}).get("conditions") or []),
        interventions=[
            f"{i.get('name', '?')} ({i.get('type', '?')})"
            for i in (p.get("armsInterventionsModule") or {}).get("interventions") or []
        ],
        sponsor=((p.get("sponsorCollaboratorsModule") or {}).get("leadSponsor") or {}).get("name"),
        summary=(p.get("descriptionModule") or {}).get("briefSummary"),
        first_posted=first,
        first_posted_raw=first_raw,
        date_imprecise=imprecise,
        start=(status.get("startDateStruct") or {}).get("date"),
        last_update=(status.get("lastUpdatePostDateStruct") or {}).get("date"),
        has_results=bool(study.get("hasResults")),
    )


def _sections(r: CtRecord) -> list[tuple[str | None, str]]:
    status = f"Status: {r.status}." + (f" Why stopped: {r.why_stopped}." if r.why_stopped else "")
    paras = [
        status,
        f"Study type: {r.study_type or 'not stated'}; phase: {', '.join(r.phases) or 'not stated'}.",
    ]
    if r.conditions:
        paras.append("Conditions: " + "; ".join(r.conditions) + ".")
    if r.interventions:
        paras.append("Interventions: " + "; ".join(r.interventions) + ".")
    if r.sponsor:
        paras.append(f"Lead sponsor: {r.sponsor}.")
    paras.append(
        f"Start date: {r.start or 'not stated'}; first posted: {r.first_posted_raw or 'not stated'}; "
        f"last update posted: {r.last_update or 'not stated'}."
    )
    out: list[tuple[str | None, str]] = [("Registry record", "\n\n".join(paras))]
    if r.summary:
        out.append(("Brief summary", r.summary))
    return out


def _limitations(r: CtRecord) -> list[str]:
    lims = [
        "Registry record describes a trial, not a published result; absence of results here does not "
        "mean results do not exist elsewhere.",
        "Not necessarily the same program as the one being assessed (found by intervention/condition search).",
    ]
    if r.why_stopped:
        lims.append("Stopping reason is sponsor-reported and may be non-scientific (e.g. funding, strategy).")
    if not r.has_results:
        lims.append("No results are posted on ClinicalTrials.gov for this study.")
    if r.date_imprecise:
        lims.append("First-posted date is imprecise (year/month only); latest possible date is used.")
    lims.append("Found via ClinicalTrials.gov query: " + ", ".join(r.kinds) + ".")
    return lims


class ClinicalTrialsConnector:
    name = "ClinicalTrials.gov"

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        page_size: int = 10,
        sleep: Sleep = asyncio.sleep,
        min_interval: float = 1.3,
        max_attempts: int = 3,
        backoff: float = 1.0,
    ) -> None:
        self.client = client
        self.page_size = page_size
        self._sleep, self._max_attempts, self._backoff = sleep, max_attempts, backoff
        self.limiter = RateLimiter(min_interval, sleep=sleep)

    async def _query(self, params: dict) -> tuple[list[dict], bool]:
        resp = await get_with_retries(
            self.client, STUDIES, params={**params, "pageSize": self.page_size, "format": "json"},
            source=self.name, limiter=self.limiter, max_attempts=self._max_attempts,
            backoff=self._backoff, sleep=self._sleep,
        )
        try:
            data = resp.json()
            studies = data["studies"]
            if not isinstance(studies, list):
                raise TypeError
        except (ValueError, KeyError, TypeError) as exc:
            raise SourceUnavailable(self.name, "unexpected response format") from exc
        return studies, bool(data.get("nextPageToken"))

    async def search(
        self, *, condition: str, intervention: str, as_of: date | None = None
    ) -> ConnectorResult:
        res = ConnectorResult(source=self.name)
        if as_of:
            res.status = "skipped"
            res.warnings.append(
                f"ClinicalTrials.gov: skipped because as_of_date={as_of.isoformat()} was given. "
                "The registry returns current record versions that may contain information posted "
                "after that date; use a frozen snapshot for historical evaluation."
            )
            return res
        plan = {
            "intervention": {"query.cond": condition, "query.intr": intervention},
            "stopped": {"query.cond": condition, "query.intr": intervention, "filter.overallStatus": STOPPED},
            "competitors": {"query.cond": condition, "filter.overallStatus": COMPETITOR_STATUSES},
        }
        records: dict[str, CtRecord] = {}
        failed = 0
        for kind, params in plan.items():
            try:
                studies, more = await self._query(params)
            except SourceUnavailable as exc:
                failed += 1
                res.warnings.append(
                    f"ClinicalTrials.gov [{kind}]: source did not respond ({exc.detail}). This is NOT "
                    "evidence of absence (including absence of stopped or competing trials); retry or check manually."
                )
                continue
            parsed = [r for r in (parse_study(s) for s in studies) if r]
            if not parsed:
                res.warnings.append(f"ClinicalTrials.gov [{kind}]: the search succeeded but returned no studies.")
            if more:
                res.warnings.append(
                    f"ClinicalTrials.gov [{kind}]: more studies match than were retrieved "
                    f"(first {self.page_size} only)."
                )
            for r in parsed:
                records.setdefault(r.nct, r).kinds.append(kind)

        for r in records.values():
            res.documents.append(
                make_record_document(
                    r.title,
                    _sections(r),
                    source_type="registry",
                    url=f"https://clinicaltrials.gov/study/{r.nct}",
                    identifier=r.nct,
                    published_at=r.first_posted,
                    scope=Scope.APPROACH,
                    limitations=_limitations(r),
                )
            )
        if not records:
            res.status = "unavailable" if failed == len(plan) else "empty"
        else:
            res.status = "partial" if failed else "ok"
        return res


async def _demo(condition: str, intervention: str) -> None:
    async with httpx.AsyncClient() as client:
        res = await ClinicalTrialsConnector(client).search(condition=condition, intervention=intervention)
    print("status:", res.status)
    for w in res.warnings:
        print("WARN:", w)
    for d in res.documents:
        print(d.identifier, d.published_at, d.source_type, "|", d.title[:90])


if __name__ == "__main__":
    import sys

    asyncio.run(_demo(sys.argv[1], sys.argv[2]))