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
