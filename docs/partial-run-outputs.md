# Partial assessment outputs

Completed nodes are now saved to SQLite as soon as they return a validated
RoleResult. A later node failure no longer hides those results from the website.
GET `/runs/{run_id}/outputs` returns the saved node outputs and progress states
through the existing authenticated API and same-origin website proxy.

The website shows node summaries, positions, claims, risks, gaps, conditions and
structured analyses during a run and after failure. Failed nodes show their error;
nodes not reached remain not started. Partial outputs are explicitly separate
from a completed committee report. Saved reports and their immutability are unchanged.

During an audit repair, affected outputs are marked stale before rerunning their
owners and dependents. Earlier results remain readable with that label if repair
fails. Cancelled nodes and running nodes in a failed/restarted run are shown as
interrupted. Aggregate audit findings and Chair outputs are also checkpointed.
The display endpoint omits repeated nested upstream_context copies; the full
canonical node result remains in storage, and each ancestor has its own card.

Deploy both API and web changes together. API startup creates the additive
run_nodes table in the existing persistent SQLite database. Old runs have no
saved node outputs unless the new pipeline recorded them; historical results
cannot be reconstructed from the former in-memory state. Start a new assessment
after deployment to test checkpointing. This feature does not change request
limits, validators, node dependencies, retries or recommendations.

The supplied deployed run `run-a31c81500b11` visibly failed with
NODE_REQUEST_BUDGET. The old website exposed no node output or node identity.
This change makes new failures inspectable; it does not establish that the
underlying deployed budget failure is fixed.

Validation: 1,114 backend tests and 42 website tests passed; TypeScript, shared
contract generation checks, Ruff, formatting, production build and diff checks
passed. Pipeline/API tests verify retained outputs after failure and SQLite
reopening, stale outputs after failed repair, interruption after restart,
missing-run behavior and unchanged absence of a final report on failure.
Browser verification used a labelled synthetic local run with no model calls
or external retrieval; Science, Translation and Clinical stayed visible when
Market failed, and their details expanded normally.

Changes are local and have not been deployed to Railway.
