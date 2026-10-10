"""R3-02 entry point: build_evidence_pack(case, ctx) -> EvidencePack.

- evidence_only: no external calls; only provided documents are used.
- live: PubMed, ClinicalTrials.gov and Open Targets run in parallel under one deadline.
- any source failure/timeout = warning, never an exception; empty result = empty pack + warning.
"""
from __future__ import annotations

import asyncio
import hashlib
from dataclasses import replace

import httpx

from vic.config import Settings, get_settings
from vic.contracts import CaseInput, EvidencePack, RunContext, RunMode, RunStage

from .connectors.base import ConnectorResult, Sleep
from .connectors.clinicaltrials import ClinicalTrialsConnector
from .connectors.opentargets import OpenTargetsConnector, TargetResolution
from .connectors.pubmed import PubMedConnector, build_queries
from .importer import Annotation, ParsedDocument, build_pack

USER_AGENT = "vic-evidence/0.1 (virtual investment committee hackathon)"


def _bounded_external(groups: list[list[ParsedDocument]], settings: Settings) -> list[ParsedDocument]:
    """Keep a small, explicit sample and literal excerpts with original locators."""
    if settings.provider_input_limit_test:
        return list({doc.source_id: doc for group in groups for doc in group}.values())
    selected = []
    seen = set()
    for index in range(max((len(group) for group in groups), default=0)):
        for group in groups:
            if index >= len(group) or group[index].source_id in seen:
                continue
            doc = group[index]
            seen.add(doc.source_id)
            annotation = doc.annotations[0] if doc.annotations else Annotation(
                doc.units[0].text, doc.units[0].locator, "approach", [])
            excerpt = annotation.excerpt.encode("utf-8")[:settings.retrieval_excerpt_max_bytes].decode("utf-8", "ignore")
            if len(excerpt) < len(annotation.excerpt) and " " in excerpt:
                excerpt = excerpt.rsplit(" ", 1)[0]
            selected.append(replace(doc, annotations=[replace(annotation, excerpt=excerpt,
                limitations=[*annotation.limitations,
                    "Limited retrieval sample: omitted text may include safety or contradictory findings."])]))
            if len(selected) >= settings.retrieval_max_external_documents:
                return selected
    return selected


def _empty_pack(ctx: RunContext, warnings: list[str]) -> EvidencePack:
    sid = ctx.snapshot_id or "snap-" + hashlib.sha256(f"empty|{ctx.run_id}".encode()).hexdigest()[:12]
    return EvidencePack(sources=[], evidence=[], retrieval_warnings=warnings, snapshot_id=sid, synthetic=False)


def _finish(docs: list[ParsedDocument], warnings: list[str], ctx: RunContext) -> EvidencePack:
    if not docs:
        return _empty_pack(ctx, warnings)
    return build_pack(docs, retrieval_warnings=warnings, snapshot_id=ctx.snapshot_id).pack


async def build_evidence_pack(
    case: CaseInput,
    ctx: RunContext,
    *,
    client: httpx.AsyncClient | None = None,
    extra_documents: list[ParsedDocument] | None = None,
    overall_timeout: float = 60.0,
    sleep: Sleep = asyncio.sleep,
    settings: Settings | None = None,
) -> EvidencePack:
    extra = list(extra_documents or [])
    warnings: list[str] = []

    if ctx.mode == RunMode.EVIDENCE_ONLY:
        warnings.append(
            "evidence_only mode: external sources (PubMed, ClinicalTrials.gov, Open Targets) were not "
            "queried; the pack contains only the provided documents."
        )
        ctx.trace.log(RunStage.RETRIEVE, "evidence_only: no external calls")
        return _finish(extra, warnings, ctx)

    as_of = ctx.as_of_date or case.as_of_date
    settings = settings or get_settings()
    pubmed_limit = min(settings.retrieval_pubmed_retmax, settings.retrieval_pubmed_per_query)
    trials_limit = min(settings.retrieval_trials_page_size, settings.retrieval_trials_per_query)
    ctx.trace.log(RunStage.RETRIEVE, f"retrieval caps: PubMed={pubmed_limit}; trials={trials_limit} per query")
    own_client = client is None
    client = client or httpx.AsyncClient(headers={"User-Agent": USER_AGENT})
    try:
        jobs = {
            "PubMed": PubMedConnector.from_env(client, retmax=pubmed_limit, sleep=sleep).search(
                build_queries(case.mechanism, case.indication), as_of=as_of),
            "ClinicalTrials.gov": ClinicalTrialsConnector(client, page_size=trials_limit, sleep=sleep).search(
                condition=case.indication, intervention=case.mechanism, as_of=as_of),
            "Open Targets": OpenTargetsConnector(client, sleep=sleep).resolve(case.mechanism),
        }
        tasks = {name: asyncio.create_task(coro) for name, coro in jobs.items()}
        _done, pending = await asyncio.wait(tasks.values(), timeout=overall_timeout)
        for t in pending:
            t.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
    finally:
        if own_client:
            await client.aclose()

    external: list[ParsedDocument] = []
    groups: list[list[ParsedDocument]] = []
    for name, task in tasks.items():
        if task in pending:
            warnings.append(
                f"{name}: did not finish within {overall_timeout:.0f}s and was skipped. This is NOT "
                "evidence of absence; retry or check manually."
            )
            ctx.trace.log(RunStage.RETRIEVE, f"{name}: timeout")
            continue
        try:
            result = task.result()
        except Exception as exc:  # noqa: BLE001 - one connector failure must not stop retrieval
            warnings.append(f"{name}: unexpected error ({type(exc).__name__}); source skipped.")
            ctx.trace.log(RunStage.RETRIEVE, f"{name}: error {type(exc).__name__}")
            continue
        warnings.extend(result.warnings)
        if isinstance(result, ConnectorResult):
            external.extend(result.documents)
            groups.append(result.documents)
            ctx.trace.log(RunStage.RETRIEVE, f"{name}: {result.status}, {len(result.documents)} documents")
        elif isinstance(result, TargetResolution):
            ctx.trace.log(RunStage.RETRIEVE, f"{name}: {result.status}")

    if not external and not extra:
        warnings.append(
            "No external evidence was retrieved. Do not read this as evidence of absence: "
            "see the per-source warnings above."
        )
    bounded = _bounded_external(groups, settings)
    if external and not settings.provider_input_limit_test:
        warnings.append(f"Limited external retrieval: {len(bounded)} of {len(external)} retrieved documents, "
                        f"one excerpt per document, at most {settings.retrieval_excerpt_max_bytes} UTF-8 bytes each. "
                        "This is a partial sample, not a systematic search or evidence of absence; "
                        "omitted text may contain safety findings or contradictions.")
        ctx.trace.log(RunStage.RETRIEVE, f"external input limited: documents={len(bounded)}, "
                      f"excerpt_bytes={sum(len(d.annotations[0].excerpt.encode('utf-8')) for d in bounded)}")
    return _finish(extra + bounded, warnings, ctx)


async def _demo(indication: str, mechanism: str) -> None:
    from vic.contracts import Scope
    from vic.run_context import (
        RunContext as _,  # noqa: F401  (exists in the repo; import checks wiring)
    )

    case = CaseInput(indication=indication, mechanism=mechanism, scope=Scope.APPROACH)
    ctx = RunContext(case_id="demo", run_id="demo", snapshot_id=None, as_of_date=None, mode=RunMode.LIVE)
    pack = await build_evidence_pack(case, ctx)
    print(f"sources={len(pack.sources)} evidence={len(pack.evidence)} snapshot={pack.snapshot_id}")
    for s in pack.sources:
        print(" ", s.type, s.document_id, "|", s.title[:80])
    for w in pack.retrieval_warnings:
        print("WARN:", w)


if __name__ == "__main__":
    import sys

    asyncio.run(_demo(sys.argv[1], sys.argv[2]))
