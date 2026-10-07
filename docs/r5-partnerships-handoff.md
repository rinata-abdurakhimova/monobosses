# R5 partnerships — local handoff

Prompt ID `partnerships`, version `1.0.0`.
Entrypoint: `analyze_partnerships(case, pack, ctx, *, market=None,
ip_licensing=None, science=None, clinical=None)`.
No retrieval, upstream calls, company outreach, valuation or legal clearance.

Output covers candidate identity/category, five fit dimensions, required
competencies/resources, all four collaboration formats, project offer,
discussion gaps, timing, risks/dependencies, fit checks and conditional
investment implications. No candidate is also valid when explicitly explained.

Only new R5-owned files are added. Shared contracts and frontend are untouched.
Updated against main `7ea5e96`, which includes the R5 role IDs.
The node returns the shared `RoleResult(role_id="partnerships")`; IP input
is a shared `RoleResult` or its serialized dict. Local bridge subclasses
have been removed. R2 still needs prompt registration, pipeline and Report
assembly. Contract parsing alone does not confirm integrated execution.

The unmerged IP implementation is not copied. Input may be its serialized
RoleResult; supplied claims must use evidence from this snapshot. Tests use
explicit synthetic IP context. No evidence is inferred from agent agreement.

Payload retains full excerpts/source metadata, synthetic flag, snapshot/date,
retrieval warnings and upstream availability. Result stores trace links and
metadata under section_content[0].structured_data.partnerships.
Section key commercial_opportunity: merge with market's contribution rather
than replacing it. R1 controls display and generated frontend contracts.

R3: audit semantic excerpt support, identities and portfolio/need facts.
R4: validate stage, milestones and project offer. IP specialist: rights,
restrictions and transaction prerequisites. Interest/readiness requires direct
evidence; fit does not establish it. No claimed live readiness or final decision.

See r5-partnerships-guide.md for fields, data flow and requirement mapping.
