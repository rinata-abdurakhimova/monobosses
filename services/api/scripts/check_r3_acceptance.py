"""Rinata-requested R3-03 review: real semantic audit and blind-guess smoke checks.

Run from services/api: python scripts/check_r3_acceptance.py --output ../../artifacts/r2-r3-review
Uses only explicitly synthetic documents, existing backend credentials, bounded calls.
Does not run Market or claim that synthetic anonymization proves real-case protection.
"""
import argparse
import asyncio
import json
import time
from dataclasses import asdict
from datetime import date
from pathlib import Path

from vic.config import Settings
from vic.contracts import Claim, RunBudget, RunContext, RunMode
from vic.evidence.audit import audit_claims
from vic.evidence.audit_semantic import audit_claims_semantic
from vic.evidence.importer import build_pack, parse_json, parse_text
from vic.evidence.leakage import (
    anonymize_pack, assess_temporal, blind_identity_guess, build_leakage_report, scan_blind_pack,
)
from vic.llm import build_llm
from vic.tracing import scrub


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


class RecordingAdapter:
    def __init__(self, adapter):
        self.adapter, self.calls = adapter, []

    async def generate_structured(self, prompt_id, payload, response_model, ctx):
        try:
            result = await self.adapter.generate_structured(prompt_id, payload, response_model, ctx)
        except Exception as exc:
            print(f"{prompt_id}: {type(exc).__name__}: {getattr(exc, 'code', 'error')}: {getattr(exc, 'message', 'request failed')}", flush=True)
            raise
        self.calls.append(dict(prompt_id=prompt_id, payload=payload,
                               response=result.model_dump(mode="json")))
        return result


async def check(output):
    output.mkdir(parents=True, exist_ok=True)
    settings = Settings(llm_max_output_tokens=1024, llm_max_retries=0,
                        llm_max_repairs=1, llm_request_timeout_seconds=30)
    model = RecordingAdapter(build_llm(settings))
    ctx = RunContext(case_id="r3-review-synthetic", run_id="r3-review-live",
        snapshot_id=None, as_of_date=date(2026, 10, 9), mode=RunMode.EVIDENCE_ONLY,
        model=model, budget=RunBudget(max_seconds=120, deadline=time.monotonic() + 120))
    texts = [
        "In a mouse model, X-001 lowered marker M by 48%.",
        "A safe human exposure range for X-001 is unknown. No human safety data exist.",
        "In adult patients, X-001 increased marker M at the tested exposure.",
    ]
    documents = [parse_json(dict(title=f"Synthetic controlled result {i}", text=text,
        synthetic=True, published_at="2026-10-08",
        evidence=[dict(excerpt=text, scope="program", limitations=["Synthetic control, not a real study"])]))
        for i, text in enumerate(texts, 1)]
    imported = build_pack(documents)
    pack = imported.pack
    ctx.snapshot_id = pack.snapshot_id

    def claim(id_, text, evidence, status="supported", provenance="source"):
        return Claim(id=id_, text=text, evidence_ids=evidence, support_status=status,
                     provenance=provenance, scope="program", importance="critical")

    ev = [next(e.id for e in pack.evidence if e.excerpt == text) for text in texts]
    controls = [
        claim("science.mouse_supported", "The supplied synthetic record reports that in a mouse model, X-001 lowered marker M by 48%.", [ev[0]]),
        claim("translation.false_safety", "X-001 is safe in humans at the tested exposure.", [ev[1]]),
        claim("clinical.false_direction", "In adult patients, X-001 lowered marker M at the tested exposure.", [ev[2]]),
        claim("chair.false_human_benefit", "X-001 lowered marker M in patients.", [ev[0]]),
        claim("science.dangling", "X-001 lowers marker M.", ["ev-missing"]),
        claim("market.misattributed", "Annual pricing exceeds reimbursement benchmarks in the target region.", [ev[0]]),
        claim("translation.honest_unknown", "Safe human exposure is unknown.", [], "unknown", "ai"),
    ]
    expected = {
        "science.mouse_supported": dict(verdicts=["supported"], blocking=False),
        "translation.false_safety": dict(verdicts=["unverified", "contradicted"], blocking=True),
        "clinical.false_direction": dict(verdicts=["contradicted", "unverified"], blocking=True),
        "chair.false_human_benefit": dict(verdicts=["unverified"], blocking=True),
        "science.dangling": dict(verdicts=["unverified"], blocking=True),
        "market.misattributed": dict(verdicts=["unverified"], blocking=True),
        "translation.honest_unknown": dict(verdicts=["unknown"], blocking=False),
    }
    # Freeze expectations before looking at any provider response.
    save(output / "expected.json", expected)
    save(output / "input.json", dict(pack=pack.model_dump(mode="json"),
                                    claims=[c.model_dump(mode="json") for c in controls]))
    structural = audit_claims(controls, pack, documents=documents)
    save(output / "structural-audit.json", structural.model_dump(mode="json"))
    # Check short independent claims so this review does not depend on a large audit batch.
    audit = None
    for control in controls:
        checked = await audit_claims_semantic([control], pack, ctx, documents=documents)
        if audit is None:
            audit = checked
        else:
            audit.findings.extend(checked.findings)
            audit.unresolved_critical_claim_ids.extend(checked.unresolved_critical_claim_ids)
            audit.warnings.extend(checked.warnings)
    save(output / "semantic-audit.json", audit.model_dump(mode="json"))
    results = []
    for finding in audit.findings:
        exp = expected[finding.claim_id]
        results.append(dict(claim_id=finding.claim_id, expected=exp,
            actual=finding.model_dump(mode="json"),
            passed=finding.verdict.value in exp["verdicts"] and finding.blocking == exp["blocking"]))
    semantic_called = any(call["prompt_id"] == "audit" for call in model.calls)
    eligible = {"science.mouse_supported", "translation.false_safety", "clinical.false_direction"}
    returned = {v["claim_id"] for call in model.calls if call["prompt_id"] == "audit"
                for v in call["response"]["verdicts"]}
    audit_complete = eligible <= returned and not audit.warnings and semantic_called
    print(f"Audit controls: {sum(item['passed'] for item in results)}/{len(results)}; real semantic call: {semantic_called}", flush=True)

    text = ("SYNTHETIC ONLY. Acmedrug, developed by Acme Bio, lowered marker M in a fictional cohort. "
            "Trial NCT01234567; PMID 1234567; report https://example.org/acmedrug; DOI 10.1000/abc.123.")
    original = build_pack([parse_text("Acmedrug fictional study", text, synthetic=True,
                                      identifier="NCT01234567", published_at="2026-10-08")]).pack
    terms = ["Acmedrug", "Acme Bio"]
    blind = anonymize_pack(original, terms)
    scan = scan_blind_pack(blind.pack, terms)
    # The identity map is evaluator-only, never passed through the model adapter.
    save(output / "evaluator-map.json", asdict(blind.mapping))
    save(output / "blind-pack.json", blind.pack.model_dump(mode="json"))
    guess = await blind_identity_guess(blind, terms, ctx)
    temporal = assess_temporal(blind.pack.sources, as_of=date(2026, 10, 9),
                               model_cutoff=None, cutoff_documented=False)
    leakage = build_leakage_report(identity_findings=scan, temporal=temporal, guess=guess,
                                   method="Synthetic rule-based masking + real gateway blind guess")
    blind_calls = [call for call in model.calls if call["prompt_id"] == "blind_guess"]
    sent = json.dumps([call["payload"] for call in blind_calls]).lower()
    isolated = bool(blind_calls) and not any(value.lower() in sent for value in
        [*terms, "NCT01234567", "PMID 1234567", "10.1000/abc.123", "https://example.org", "original_titles"])
    blind_ok = guess.performed and isolated and not scan
    # No documented model cutoff: this check must never claim temporal protection.
    honest = leakage["overall"] != "controlled_as_tested"
    save(output / "leakage.json", leakage)
    print(f"Blind guess performed: {guess.performed}; identity-map isolation: {isolated}; leakage: {leakage['overall']}", flush=True)
    passed = all(item["passed"] for item in results) and audit_complete and blind_ok and honest
    review = dict(passed=passed, model=settings.llm_model, audit_controls=results,
        semantic_audit_complete=audit_complete, blind_guess_performed=guess.performed,
        identity_mapping_isolated=isolated, direct_leaks=[asdict(item) for item in scan],
        leakage=leakage, usage=ctx.trace.usage,
        cost_usd=None if ctx.budget.cost_unavailable else ctx.budget.spent_cost_usd,
        limitations=["Synthetic control cases only; not real-world accuracy or leakage protection.",
                     "No documented model cutoff; temporal control is partial.",
                     "Full committee live completion remains a separate integration task."])
    secrets = [settings.llm_api_key, settings.api_shared_secret]
    save(output / "model-calls.json", scrub(model.calls, secrets))
    save(output / "review.json", scrub(review, secrets))
    print("PASS" if passed else "FAIL (review.json contains actual results)", flush=True)
    return 0 if passed else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    return asyncio.run(asyncio.wait_for(check(args.output), timeout=120))


if __name__ == "__main__":
    raise SystemExit(main())
