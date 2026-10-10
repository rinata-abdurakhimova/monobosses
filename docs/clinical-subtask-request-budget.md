# Clinical subtask request budget

Clinical now runs four sequential tasks with separate prompts, output schemas and scoped inputs:

1. Population, comparator, standard of care and unmet need.
2. Endpoints, biomarkers and trial-size basis.
3. Safety requirements and unresolved safety gaps.
4. Development sequence, regulatory context and overall feasibility, including the preceding task results.

These calls use the configured model. Python assembles their outputs and validates the existing Clinical analysis and RoleResult contracts. Full Science and Translation results remain unchanged. Relevant prior claims are scoped per task; critical claims, risks, gaps and limitations are shared. Exact selected evidence excerpts are available to every task. Retrieval itself is unchanged.

`CLINICAL_REQUEST_TARGET_BYTES=10000` defaults to a 10,000-byte full serialized request budget, including system prompt, schema, feedback and provider envelope. Initial calls reserve 512 bytes for the existing bounded correction (one compact validation error, no replay of an invalid answer). The completion cap remains 4,096 tokens. Existing Clinical reasoning-effort settings apply to all these calls for OpenAI-compatible providers.

Oversized scoped input is serialized and split into measured UTF-8-safe segments. Every segment is reviewed with a bounded review schema. Adjacent reviews are combined through measured calls when necessary. Stable record identifiers, provenance and citation metadata remain in a catalogue. Final task synthesis receives this catalogue and the reviews; its limitations explicitly disclose use of AI reviews. No selected segment is silently dropped. Reviews can nevertheless omit scientific nuance; domain review remains necessary, and schema validation does not establish clinical truth.

The budget is bytes, not tokens. It must be below the gateway's actual input limit. A 5,000-byte gateway may still reject a task whose schema, case metadata or audit feedback alone exceeds that limit. Such requests stop with a controlled `clinical_request_budget` failure rather than truncating metadata or sending an oversized request. A provider context rejection during a direct request or segment review triggers smaller segment budgets. Other provider errors propagate normally.

Tests cover four-task assembly, scoped prior claims, preservation of complete original inputs, Unicode segment coverage, compact repairs under the budget, feedback retention, unchanged completion cap, preflight failure for indivisible oversized metadata, and the scripted HTTP workflow. These are local tests, not a live gateway or deployed Clinical verification. More review calls increase latency and cost.
