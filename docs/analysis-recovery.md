# Specialist analysis recovery

A specialist can have substantive findings while its overall position remains
`insufficient_data`. This position indicates incomplete evidence for a conclusion,
not necessarily an empty analysis. In contrast, `node_recovery.status =
analysis_unavailable` means the output was rejected and no conclusions were retained.
The website distinguishes these outcomes and shows claim, risk and gap counts.

For approach assessments, shared generation instructions require approach-scoped
claims, contextual candidate examples with applicability limitations, and explicit
diligence gaps for missing candidate information. Program assessments retain their
program scope. A program-scoped result in an approach assessment gets one targeted
regeneration with the incompatible claim IDs before fallback. No claims are simply
relabeled, and the scope validator remains enforced.

Domain ValueErrors raised by specialist validation after schema generation also
get one regeneration with sanitized validation feedback. A repeated error is
recorded in node_recovery.validation_reason and the trace. Schema repair remains
owned by the shared adapter. Authentication and transport errors are not converted
to evidence gaps. A specialist has at most one additional full invocation for
scope/domain repair; its internal model calls and schema retries still apply.
This can add provider latency and cost. Repair feedback is restored afterward.

Deploy API and website together, then create a new assessment to check the change.
Old reports and checkpoints are not rewritten. Resume may reuse a completed
unavailable checkpoint, so it is not a substitute for a new assessment when testing
this repair. Imported evidence requires an explicit new/review run.

Recovery improves correctness and diagnostics; it does not create absent clinical,
commercial or IP evidence or establish live-model quality. Genuine unknowns remain.


## Preliminary conclusions with partial evidence

Clinical, Market and Partnerships outputs with an insufficient_data overall
position and at least one supported, mixed or contradicted claim with evidence
references become partial_assessment at the shared RoleResult boundary. The
original position is retained in assessment_coverage metadata; summaries, claim
support statuses, risks, unknowns and conditions are unchanged. This describes
usable partial output, not established readiness, attractive economics or partner
interest. Empty/unknown-only and rejected outputs retain their existing status.

Prompts require substantive summaries distinguishing established findings,
conditional implications and specific next diligence steps. The website shows
preliminary conclusions and the first four claims, prioritizing evidence-linked
findings, without expanding details. All remaining claims stay available. Saved
Clinical/Market/Partnerships results get the same presentation when they meet
these criteria; saved report data is not rewritten. Specific licensing, safety
and pricing gaps remain visible.


## Clinical duplicate-claim repair

Clinical subtask models enforce unique claim keys before their outputs are merged.
Previously, two differently worded claims with the same key could pass a subtask
schema and fail the whole ClinicalPlanAnalysis root validator only at assembly.
The shared schema repair now receives the duplicate keys and regenerates the
faulty subtask; other completed subtasks are retained. Conflicting duplicates are
not silently discarded or relabeled. If repair fails, normal recovery still applies.

Root validation diagnostics include the rule message and a <root> location, with
input/context omitted and configured secrets scrubbed. A displayed : value_error
alone does not prove which rule failed in a historical run. This duplicate-claim
failure has been reproduced with a test provider; confirmation for a production
run requires its original traceback/trace or a new run with the improved diagnostics.


## Investment stage validation and retained plans

Investment performs one targeted domain repair of its planning stage or financial
explanation when using the shared adapter with repairs enabled. Explanation repair
reuses the same fixed_plan hash and Python calculated_financials; it does not
regenerate a validated plan. Input binding, arithmetic, reference and qualitative
narrative checks remain enforced. At most one additional generation per stage is
performed; shared schema repair and existing pipeline recovery limits still apply.

With continue_on_node_validation_error enabled, an explanation that remains
invalid yields a partial_assessment containing the validated planning claims,
risks, work packages, fixed plan and Python calculations. Rejected explanation
claims, financial-path conclusions and narrative numbers are omitted. The exact
sanitized reason is retained under investment.explanation_recovery, and the
committee cannot issue unconditional Invest based on this incomplete specialist.
A plan that fails its own validation is not retained as if it were valid.
Provider authentication/transport failures still propagate normally.


Planning risk recovery normalizes foreign/missing Investment ID prefixes without
changing the description or existing claim references. ID collisions remain
distinct; duplicate input IDs remain invalid. A risk without claim references is
retained verbatim as an unvalidated proposal in unknowns, including impact and
next check, rather than assigned fabricated support or allowed to invalidate all
other findings. Unknown nonempty claim references still require correction.


Uncertain Investment claims without assumptions are retained with an explicit
model-omitted-rationale verification gap before plan and explanation validation.
Existing text, evidence references and support status remain unchanged. No source
support or domain assumption is invented. Empty/whitespace-only rationale is
handled; repeated qualification is idempotent. This prevents a missing explanatory
field from discarding an otherwise valid assessment while exposing its limitation.


## Short committee pipeline

SHORT_COMMITTEE=true is now the default. Science, Translation, Clinical, Market,
IP/Licensing, Partnerships and Investment run, then a separate concise Chair
synthesizes a one- or two-sentence rationale. Investment Threshold, Failure Miner
and Semantic Audit are not invoked or required, and do not enter Chair input.
Their source files remain available. No audit call is made on Chair claims; the
short Chair creates no new factual claims and can only reference existing IDs.
Its recommendation is Invest, Conditional or Do Not Invest, explicitly preliminary.
The three excluded nodes do not block Invest. Unresolved critical claims or an
unavailable specialist analysis in the seven included nodes require Conditional
instead of Invest.
The usual report schema, seven expert sections, evidence links and immutable
versions remain. Five diligence questions are assembled from specialist gaps to
retain report compatibility, separate from the short recommendation.

The website hides these three role cards in live progress, saved reports and
synthetic previews, with corrected perspective counts. The API outputs endpoint
also omits disabled nodes in short mode. Short-mode resume can reuse the completed
seven specialists of a run that previously failed at Threshold; it skips the old
Threshold/Failure Miner/audit results and goes to short synthesis.

Deploy API and web from this branch, set SHORT_COMMITTEE=true (or leave the default),
restart services, and start a new assessment or resume a eligible failed run.
SHORT_COMMITTEE=false retains the full backend pipeline for later use. Website
role visibility remains reduced. This change does not replace evidence validation
or prove a successful real-provider run; local integration uses labelled stubs.
