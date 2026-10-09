#!/usr/bin/env python3
"""R4-03 paired evaluation runner (issue #16).

Runs Science -> Translation -> Clinical on each manifest family's before/after
snapshot through a real LLM adapter and scores outputs against evaluator-only
expectations. There are no canned responses: without --adapter the runner only
validates the manifest.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime
import hashlib
import importlib
import json
import logging
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
API_SRC = REPO_ROOT / "services" / "api" / "src"
if str(API_SRC) not in sys.path:
    sys.path.insert(0, str(API_SRC))

from vic.agents.science.clinical import PROMPT_VERSION as CLINICAL_PROMPT_VERSION  # noqa: E402
from vic.agents.science.clinical import analyze_clinical  # noqa: E402
from vic.agents.science.scientific import PROMPT_VERSION as SCIENCE_PROMPT_VERSION  # noqa: E402
from vic.agents.science.scientific import analyze_science  # noqa: E402
from vic.agents.science.translation import PROMPT_VERSION as TRANSLATION_PROMPT_VERSION  # noqa: E402
from vic.agents.science.translation import analyze_translation  # noqa: E402
from vic.contracts import CaseInput, EvidencePack, LlmAdapter, RoleResult, RunContext, RunMode  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("r4_runner")

Snapshot = tuple[RoleResult, RoleResult, RoleResult]


def _status(value: Any) -> str:
    return str(getattr(value, "value", value))


def _opaque_id(family_id: str) -> str:
    # Family ids encode the expected outcome; never expose them to the model.
    return "r4eval-" + hashlib.sha256(family_id.encode("utf-8")).hexdigest()[:12]


def _check_pack_integrity(family_id: str, sources: list[dict], evidence: list[dict]) -> None:
    source_ids = [s["id"] for s in sources]
    evidence_ids = [e["id"] for e in evidence]
    if len(source_ids) != len(set(source_ids)) or len(evidence_ids) != len(set(evidence_ids)):
        raise ValueError(f"{family_id}: duplicate source or evidence ids in snapshot")
    orphans = sorted({e["source_id"] for e in evidence} - set(source_ids))
    if orphans:
        raise ValueError(f"{family_id}: evidence references unknown sources {orphans}")


def build_packs(family: dict[str, Any]) -> tuple[EvidencePack, EvidencePack]:
    family_id = family["family_id"]
    before, after = family["before"], family["after"]

    before_sources, before_evidence = before["sources"], before["evidence"]
    after_sources = [*before_sources, *after.get("added_sources", [])]
    after_evidence = [*before_evidence, *after.get("added_evidence", [])]

    _check_pack_integrity(family_id, before_sources, before_evidence)
    _check_pack_integrity(family_id, after_sources, after_evidence)

    def _pack(snapshot_id: str, sources: list[dict], evidence: list[dict]) -> EvidencePack:
        return EvidencePack.model_validate(
            {
                "snapshot_id": snapshot_id,
                "sources": sources,
                "evidence": evidence,
                "synthetic": all(s["synthetic"] for s in sources),
            }
        )

    return (
        _pack(before["snapshot_id"], before_sources, before_evidence),
        _pack(after["snapshot_id"], after_sources, after_evidence),
    )


async def _run_snapshot(
    case: CaseInput, pack: EvidencePack, adapter: LlmAdapter, opaque_id: str, label: str
) -> Snapshot:
    ctx = RunContext(
        case_id=opaque_id,
        run_id=f"{opaque_id}-{label}",
        snapshot_id=pack.snapshot_id,
        as_of_date=None,
        mode=RunMode.EVIDENCE_ONLY,
        model=adapter,
    )
    sci = await analyze_science(case, pack, ctx)
    trans = await analyze_translation(case, pack, ctx)
    clin = await analyze_clinical(case, pack, sci, trans, ctx)
    return sci, trans, clin


def _claims(results: Snapshot) -> dict[str, Any]:
    return {c.id: c for r in results for c in r.claims}


def _risk_ids(results: Snapshot) -> set[str]:
    return {risk.id for r in results for risk in r.risks}


def _dump(results: Snapshot) -> dict[str, Any]:
    return {
        "positions": {_status(r.role_id): r.position for r in results},
        "claims": {
            c.id: {"status": _status(c.support_status), "evidence_ids": list(c.evidence_ids)}
            for r in results
            for c in r.claims
        },
        "risks": sorted(_risk_ids(results)),
    }


def score(expectations: dict[str, Any], before: Snapshot, after: Snapshot) -> list[str]:
    b_claims, a_claims = _claims(before), _claims(after)
    b_risks, a_risks = _risk_ids(before), _risk_ids(after)
    failures: list[str] = []

    def status_of(index: dict[str, Any], key: str) -> str | None:
        claim = index.get(key)
        return _status(claim.support_status) if claim else None

    for item in expectations.get("changed_claims", []):
        key = item["claim_id"]
        got_before, got_after = status_of(b_claims, key), status_of(a_claims, key)
        if got_before != item["before_status"]:
            failures.append(f"{key}: before expected '{item['before_status']}', got '{got_before}'")
        if got_after != item["after_status"]:
            failures.append(f"{key}: after expected '{item['after_status']}', got '{got_after}'")
        cited = set(a_claims[key].evidence_ids) if key in a_claims else set()
        missing = [eid for eid in item.get("required_evidence_ids", []) if eid not in cited]
        if missing:
            failures.append(f"{key}: after-run claim does not cite required evidence {missing}")

    for key, expected in expectations.get("unchanged_claims", {}).items():
        for label, index in (("before", b_claims), ("after", a_claims)):
            got = status_of(index, key)
            if got != expected:
                failures.append(f"{key}: {label} expected unchanged '{expected}', got '{got}'")

    for key, allowed in expectations.get("tolerated_claims", {}).items():
        got = status_of(a_claims, key)
        if got not in allowed:
            failures.append(f"{key}: after status '{got}' not in tolerated {allowed}")

    for rule in expectations.get("forbidden_citations", []):
        for claim in a_claims.values():
            if claim.id.startswith(rule["claim_prefix"]) and rule["evidence_id"] in claim.evidence_ids:
                failures.append(f"{claim.id}: cites forbidden evidence {rule['evidence_id']}")

    for risk_id in expectations.get("unchanged_risks", []):
        for label, ids in (("before", b_risks), ("after", a_risks)):
            if risk_id not in ids:
                failures.append(f"risk {risk_id}: missing in {label} run")

    for key in expectations.get("missing_links_preserved", []):
        got = status_of(a_claims, key)
        if got != "unknown":
            failures.append(f"{key}: missing translation link closed without evidence (after='{got}')")

    return failures


async def evaluate_family(family: dict[str, Any], adapter: LlmAdapter, adapter_spec: str) -> dict[str, Any]:
    family_id = family["family_id"]
    case = CaseInput.model_validate(family["case"])
    pack_before, pack_after = build_packs(family)
    opaque_id = _opaque_id(family_id)

    record: dict[str, Any] = {
        "family_id": family_id,
        "kind": family.get("kind"),
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "snapshots": {"before": pack_before.snapshot_id, "after": pack_after.snapshot_id},
        "versions": {
            "science_prompt": SCIENCE_PROMPT_VERSION,
            "translation_prompt": TRANSLATION_PROMPT_VERSION,
            "clinical_prompt": CLINICAL_PROMPT_VERSION,
            "adapter": adapter_spec,
        },
    }
    try:
        before = await _run_snapshot(case, pack_before, adapter, opaque_id, "s1")
        after = await _run_snapshot(case, pack_after, adapter, opaque_id, "s2")
    except Exception as exc:  # an agent/schema failure is a scored failure, not a runner crash
        record.update(passed=False, failures=[f"run error: {type(exc).__name__}: {exc}"])
        return record

    failures = score(family["expectations"], before, after)
    record.update(passed=not failures, failures=failures, before=_dump(before), after=_dump(after))
    return record

def load_adapter(spec: str) -> LlmAdapter:
    module_name, _, attr = spec.partition(":")
    module = importlib.import_module(module_name)
    if not attr:
        obj: Any = module  # module exposing a module-level async generate_structured, e.g. vic.llm
    else:
        obj = getattr(module, attr)
        if isinstance(obj, type) or not hasattr(obj, "generate_structured"):
            obj = obj()
    if not hasattr(obj, "generate_structured"):
        raise SystemExit(f"{spec} does not provide generate_structured")
    return obj


async def main() -> None:
    parser = argparse.ArgumentParser(description="R4 paired evaluation runner")
    parser.add_argument("--manifest", type=Path, default=REPO_ROOT / "evals/cases/r4_paired_manifest.json")
    parser.add_argument("--output", type=Path, default=REPO_ROOT / "evals/results/r4_paired_results.jsonl")
    parser.add_argument(
        "--adapter",
        help="'package.module' (module-level generate_structured, e.g. vic.llm) or 'module:attr'",
    )
    parser.add_argument("--validate-only", action="store_true", help="Validate manifest and packs; run no model")
    args = parser.parse_args()

    if not args.manifest.exists():
        logger.error("Manifest not found: %s", args.manifest)
        sys.exit(1)

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    families = manifest["families"]
    for family in families:
        CaseInput.model_validate(family["case"])
        build_packs(family)
    logger.info("Manifest %s: %d families valid", manifest.get("manifest_version"), len(families))

    if args.validate_only:
        return
    if not args.adapter:
        logger.warning(
            "No --adapter given: manifest validated, evaluation skipped, no results written. "
            "Run with --adapter vic.llm once the R2-02 adapter is implemented."
        )
        return

    adapter = load_adapter(args.adapter)
    args.output.parent.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, Any]] = []
    with args.output.open("w", encoding="utf-8") as out:
        for family in families:
            logger.info("Evaluating %s", family["family_id"])
            result = await evaluate_family(family, adapter, args.adapter)
            results.append(result)
            out.write(json.dumps(result, ensure_ascii=False) + "\n")
            verdict = "PASS" if result["passed"] else f"FAIL {result['failures']}"
            logger.info("[%s] %s", verdict, family["family_id"])

    passed = sum(r["passed"] for r in results)
    logger.info("Summary: %d/%d paired families passed (manifest %s).",
                passed, len(results), manifest.get("manifest_version"))
    sys.exit(0 if passed == len(results) else 1)

if __name__ == "__main__":
    asyncio.run(main())