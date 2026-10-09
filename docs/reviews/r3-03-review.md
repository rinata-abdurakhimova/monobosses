# R3-03 review requested by Rinata

Date: 9 October 2026 (Europe/Kiev). Baseline: main `a060c26`.
Checks executed by Codex at Rinata's explicit request; this is an internal
implementation review, not an external expert evaluation.

## Regression verification

```powershell
cd services/api
python -m pytest tests/vic/evidence -q
python scripts/check_r3_acceptance.py --output ../../artifacts/r2-r3-review-final
```

87 R3 regression tests passed. The live acceptance script passed all seven
controlled claims plus a real blind-guess call. Domain audit/leakage code and
prompts were not changed; this commit adds only the review harness and record.

## Expected versus actual claims

Expectations are written to expected.json before model requests. Full synthetic
inputs, structural/semantic audit outputs, blind pack, evaluator-only mapping,
model responses and usage are recorded in the output directory.

| Control | Expected | Actual | Blocking |
| --- | --- | --- | --- |
| Supplied synthetic record reports the mouse result | supported | supported | No |
| Safe exposure claimed despite no human safety data | unverified or contradicted | unverified | Yes |
| Decrease claimed when the human excerpt reports an increase | contradicted or unverified | contradicted | Yes |
| New Chair claim turns mouse evidence into human benefit | unverified | unverified | Yes |
| Missing evidence ID | unverified | unverified | Yes |
| Pricing claim cites an unrelated mouse experiment | unverified | unverified | Yes |
| Honest unknown with no supporting evidence | unknown | unknown | No |

Manual review: the supporting claim explicitly describes the supplied fictional
record; it makes no real-world efficacy assertion. The safe-exposure excerpt says
the range is unknown and human safety data do not exist. The direction-control
excerpt says increased, while the claim says lowered. The Chair's human-benefit
claim cites mouse data only. Missing/unrelated citations do not support their
claims. An honest missing-data claim is a gap, not a factual blocker.

Real semantic audit was executed for the first three claims. The other four are
handled by R3's actual deterministic checks; failed deterministic claims are not
sent to the model to be rescued. All three eligible claim IDs were present in the
real model responses, without fallback warnings in the final run.

## Actual gateway calls

Model: `gpt-6-luna`. Output allowance: 1024. Provider retries: 0; schema repairs
allowed: 1; request timeout: 30 seconds; overall review deadline: 120 seconds.

| Prompt | Content hash | Input tokens | Output tokens | Latency ms |
| --- | --- | --- | --- | --- |
| audit (mouse control) | 353cda17c7ea | 670 | 166 | 1984 |
| audit (missing safety) | 353cda17c7ea | 663 | 162 | 2234 |
| audit (opposite direction) | 353cda17c7ea | 662 | 164 | 2390 |
| blind_guess | 775d880ea077 | 323 | 76 | 1437 |

Cost unavailable because pricing is not configured; it is not reported as zero.
Saved backend provider/model configuration was not modified.

## Blind guessing and temporal limits

A fictional Acmedrug/Acme Bio document with URL, DOI, PMID and trial ID was
anonymized by the actual R3 function. Original names and IDs were absent from the
blind model payload; the evaluator mapping remained separate. The leakage scan
found no direct or possible-code residues on this control.

The real model returned candidate_names=[], confidence=low, and explained that
the evidence was synthetic and contained no identifying facts. The result records
performed=true and identified=false. This is a synthetic wiring/control test,
not evidence that real cases cannot be re-identified.

No documented model training cutoff was supplied. Temporal control correctly
remains partially_controlled and overall leakage is partial, with limitations.
No claim of controlled temporal evaluation or real-world anonymity is made.

## Earlier attempts and integration follow-up

The initial three-claim semantic batch was rejected by the gateway and correctly
returned a structural-only warning. The final review uses separate, bounded
single-claim audit calls. Large-batch gateway compatibility is not established by
this review and remains R2 runtime/request-sizing work under #7.

An earlier supported control asserted an unqualified mouse result from a synthetic
source; the model conservatively rejected real-study verification. The final
control explicitly says the synthetic record reports the result, and expected
support was frozen before that new run. Failed attempts remain in separate local
artifact directories rather than being presented as passes.

R3's implementation and standalone checks are reviewed. Full committee live
completion, production batch sizing, deployment and evaluation on real blinded
cases remain separate #7/#17/#19 acceptance work.
