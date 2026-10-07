"""Pipeline: validate -> retrieve -> analyze -> audit -> synthesize -> finalize.

STUB in R2-01; implemented in R2-02 (issue #7). Order (contract section 4):
  R3 build_evidence_pack -> science/translation/market in parallel -> clinical (reads
  science+translation) -> investment (reads clinical+market) -> R3 audit_claims ->
  R5 synthesize_committee -> R3 audit of chair claims -> report_builder -> validation.
Agents never call each other; only the pipeline does.
"""
from vic.run_context import RunContext


async def execute_run(ctx: RunContext) -> None:
    raise NotImplementedError("Pipeline is implemented in R2-02 (#7)")