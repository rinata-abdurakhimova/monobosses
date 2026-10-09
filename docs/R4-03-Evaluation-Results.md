# [R4-03] Evaluation Results & Paired Regression Verification

**GitHub Issue:** [#16](https://github.com/rinata-abdurakhimova/monobosses/issues/16)
**Assignee:** R4 (Science / Translation / Clinical) — Arina Khmel
**Reviewer:** Rinata Abdurakhimova
**Manifest:** `evals/cases/r4_paired_manifest.json` (`r4-03.v1`, split `development`, labels `team-reviewed`, synthetic)

> **Status: NOT YET RUN.** No live-adapter evaluation has been executed. All "Actual" columns are TBD. Earlier mock-generated results were removed and must not be cited.

The PR branch includes the current backend from `main`. The R4 runner's `vic.llm`
option constructs the backend's `StructuredLlm` adapter using `services/api/.env`
and environment overrides. Each snapshot uses the configured run timeout and cost
budget. It records prompt content hashes and model/provider names; raw exception
text is excluded from result files. The committed JSONL contains historical
failures from the old backend stub, not results for this integrated revision.

---

## 1. Scope

The test checks that Science, Translation and Clinical agents update only the claims a new piece of evidence actually affects. Each family runs twice: on the `before` snapshot, then on `before` plus the `added_*` items. Expectations are evaluator-only and never reach the model. The model gets an opaque case id, not the family id.

### Status vocabulary

| Layer | Values | Where used |
| :--- | :--- | :--- |
| Claim `support_status` | `supported`, `contradicted`, `mixed`, `unverified`, `unknown` | All claims; all expectations in this document |
| Translation link `status` | `established`, `partially_established`, `gap`, `unknown` | Internal to `TranslationAnalysis.links` only |

Link statuses map to claim statuses as `established → supported`, `partially_established → mixed`, `gap/unknown → unknown`. A positive link status with no valid evidence becomes `unknown`. "Established" is never a claim status.

---

## 2. Case families

### Pair A: negative, candidate-specific hepatotoxicity (`pair_a_negative_candidate_hepatotoxicity`)
- **Case:** SYN-TYK-201, oral allosteric TYK2 (JH2) inhibitor, plaque psoriasis, Phase 1, scope `program`.
- **Added evidence:** `ev-a-ph1-hepatotox`. At 300 mg QD, 3 of 8 participants had ALT >5× ULN, reversible on withdrawal. Tolerated doses (25–100 mg) stayed below the projected efficacious AUC. `ev-a-ph1-metabolite` is a scaffold-specific reactive acyl-glucuronide.
- **Principle:** a candidate's attrition must not invalidate the TYK2 approach. The P1104A genetics, IL-23/IL-12 pathway selectivity and class Phase 3 evidence are unaffected.

### Pair B: positive human target engagement (`pair_b_positive_target_engagement`)
- **Case:** SYN-AAT-301, GalNAc-siRNA against SERPINA1, PiZZ AATD liver disease, Phase 1/2, scope `program`.
- **Added evidence:** `ev-b-ph1-pd`. Median serum Z-AAT fell 87% at week 12 (200 mg), and intrahepatic Z-AAT fell 70% at week 24 (n=6). `ev-b-ph1-safety` reports no treatment-related SAEs over 24 weeks.
- **Principle:** closing the target-engagement gap must not imply patient benefit (no fibrosis-stage data yet). It also must not imply long-term hepatic or pulmonary safety, since silencing SERPINA1 lowers circulating AAT.

### Pair C: irrelevant update (`pair_c_irrelevant_other_candidate`)
- **Case:** LPA1 antagonism in IPF, Phase 2, scope `approach`.
- **Added evidence:** `ev-c-pde4b` (GI intolerance with a PDE4B inhibitor, a different candidate and mechanism) and `ev-c-admin` (sponsor name change).
- **Principle:** zero drift. Neither item may be cited by any `science.*`, `translation.*` or `clinical.*` claim.

---

## 3. Paired evaluation table

| Family | Expected changed claims (before → after) | Expected unchanged / preserved | Actual | Pass/Fail |
| :--- | :--- | :--- | :--- | :--- |
| **A** TYK2 / psoriasis | `translation.safe_exposure` unknown → **contradicted**<br>`translation.therapeutic_window` unknown → **contradicted**<br>`translation.human_exposure` unknown → **mixed**<br>`clinical.safety_requirements` mixed → **contradicted**<br>`clinical.next_milestone` mixed → mixed (premise: backup chemotype)<br>All must cite `ev-a-ph1-hepatotox` (`next_milestone` also `ev-a-ph1-metabolite`) | `science.genetic_evidence`, `pathway_biology`, `target_validation`, `prior_programs` = supported<br>`translation.molecular_effect` = supported; `target_engagement`, `patient_benefit` = unknown<br>`clinical.target_population` = supported<br>Tolerated: `clinical.study_sequence` ∈ {mixed, contradicted, unverified}<br>Forbidden: `ev-a-ph1-*` cited by `science.*`<br>Risks: `science.risk.jak_selectivity`, `clinical.risk.safety`, `clinical.risk.competitive_bar` | TBD | TBD |
| **B** AAT / liver | `translation.target_engagement` unknown → **supported**<br>`translation.biological_response` unknown → **mixed**<br>`clinical.biomarker_strategy` unverified → **supported**<br>All must cite `ev-b-ph1-pd` | `science.pathway_biology`, `animal_model_evidence` = supported; `science.target_validation` = mixed<br>`translation.molecular_effect` = supported; `patient_benefit` = unknown<br>`clinical.target_population` = supported<br>Tolerated: `human_exposure` ∈ {unknown, mixed, supported}; `safe_exposure` ∈ {unknown, mixed}; `clinical.safety_requirements` ∈ {unknown, mixed, unverified}<br>Risks: `science.risk.fibrosis_reversibility`, `translation.risk.lung_protection`, `clinical.risk.safety`, `clinical.risk.surrogate_endpoint` | TBD | TBD |
| **C** LPA1 / IPF | None | 14 claims unchanged (see manifest), including `science.causal_vs_correlative` = mixed, `translation.patient_benefit` = mixed, and `translation.human_exposure` / `target_engagement` / `biological_response` / `safe_exposure` = unknown<br>Forbidden: `ev-c-pde4b`, `ev-c-admin` in any role<br>Risks: `science.risk.redundant_fibrotic_pathways`, `translation.risk.exposure_unknown`, `clinical.risk.safety`, `clinical.risk.endpoint_variability` | TBD | TBD |

Pass criteria per family: every changed, unchanged and tolerated status matches; required evidence ids are cited; there are no forbidden citations; every listed risk id is present in both runs; and the `missing_links_preserved` links remain `unknown`.

Unexpected status changes, claim appearance/disappearance outside declared
expectations, and scope drift also fail. Claim text and assumptions are retained
for manual review: a same-status milestone change requires review of the changed
premise, beyond the automated status/citation checks. The paired unit tests use
the runner's scoring function rather than a separate evaluator.

---

## 4. Run record (fill after the first live run)

| Field | Value |
| :--- | :--- |
| Run date (UTC) | TBD |
| Adapter / model | TBD |
| Prompt versions (science / translation / clinical) | TBD |
| Results file | `evals/results/r4_paired_results.jsonl` |
| Families passed | TBD / 3 |

---

## 5. Commands

```bash
# Validate the manifest and evidence packs only (no model call, no results written)
python evals/r4_evaluation_runner_stub.py --validate-only

# Live paired evaluation
python evals/r4_evaluation_runner_stub.py --adapter vic.llm --output artifacts/pr55/r4-live-results.jsonl

# Unit / behavioural tests
pytest services/api/tests/vic/agents/science/test_paired_behavior.py -v
pytest services/api/tests/vic/agents/science/test_r4_runner.py -v
```

For whole-workflow testing, follow `docs/r2-full-workflow-handoff.md`: start the API
with `RUN_BACKEND=pipeline` and `DEV_STUBS=false`, then run
`python services/api/scripts/check_workflow.py --output artifacts/pr55/workflow --revision`.
This exercises all report roles, PDF evidence import, and an explicit report
revision while verifying that the original report stays unchanged. Live model
quality for these three R4 families still requires running the command above and
reviewing the recorded claims; deterministic tests do not establish it.

## Integration review validation

- Backend suite: `pytest services/api/tests -q` — **1,013 passed**, including the
  full HTTP workflow tests for all roles, imported evidence and immutable revisions.
- R4 suite: `pytest services/api/tests/vic/agents/science -q` — **76 passed**.
- Manifest validation: `--validate-only` — **3 families valid**, no model calls.
- Ruff on the changed Python files and `git diff --check` pass.

These are deterministic integration/regression results; live model outcomes in
the table above remain TBD.
