# VIC API (services/api) — R2

FastAPI with contract v1, SQLite storage and background orchestration. `POST
/cases/{case_id}/runs` returns 202 with a run ID; poll `GET /runs/{run_id}` for
queued/running/completed/failed, stage, usage, timing and report version.

**Live completion of #7 is pending:** the real R5 committee chair
(`synthesize_committee`, issue #13) is absent. R2 wires the existing R3 synchronous
auditor, R4 science/translation/clinical and R5 market/investment functions.
Both contract investment inputs and R5's keyword upstream inputs are supported.
Synthetic tests verify orchestration, not real model calls or analysis quality.

## Install and development

From the repository root:

```bash
cd services/api
python -m venv .venv
source .venv/bin/activate          # PowerShell: .venv\Scripts\Activate.ps1
pip install -e ".[dev,anthropic]"
cp .env.example .env              # PowerShell: Copy-Item .env.example .env
python -m uvicorn vic.main:app --reload --port 8000
```

The example enables `DEV_STUBS=true`, explicitly synthetic development mode.
Set `API_SHARED_SECRET` to a local value and configure the same value on the
Next.js server. It forwards `X-API-Key`; never expose the secret in browser code.
Swagger is at `/docs`; `/health` stays public. Do not commit `.env` or keys.

```bash
curl http://localhost:8000/health
curl -X POST http://localhost:8000/cases -H "X-API-Key: change-me" -H "Content-Type: application/json" -d '{"indication":"Synthetic X","mechanism":"Synthetic Y inhibition","scope":"approach"}'
# Replace CASE_ID with the returned case_id:
curl -X POST http://localhost:8000/cases/CASE_ID/runs -H "X-API-Key: change-me" -H "Content-Type: application/json" -d '{"mode":"live"}'
# Replace RUN_ID with the returned run_id:
curl http://localhost:8000/runs/RUN_ID -H "X-API-Key: change-me"
curl http://localhost:8000/cases/CASE_ID/reports/1 -H "X-API-Key: change-me"
```

Use `Invoke-RestMethod` or `curl.exe` on Windows PowerShell. The run body is
`RunCreate`; there is no `POST /runs` or `input_text` endpoint.

## Production handoff

Run a **single process/worker and a single replica**. Background tasks execute
in process; this is not a durable job queue. `python -m vic` serves configured
HOST/PORT. Railway uses `python scripts/serve.py` with a single IPv4/IPv6 socket;
see [deployment](../../docs/deployment.md).

Required deployment settings:

- `APP_ENV=production`, `RUN_BACKEND=pipeline`, `DEV_STUBS=false`.
- `API_SHARED_SECRET`: a real server secret; production refuses an empty value.
- `DATABASE_URL=sqlite:////data/vic.sqlite3`: use a persistent writable volume.
  Relative development default: `sqlite:///./data/vic.sqlite3`.
- `SEED_SYNTHETIC=false`: avoid fixture cases on production.
- `CORS_ORIGINS`: explicit frontend origins; production refuses `*`.
- `LLM_PROVIDER=openai`, `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY`: configure the
  mentor gateway as described below. HTTPX is already a runtime dependency.
  Alternatively use `LLM_PROVIDER=anthropic` and install the `anthropic` extra.
  R2 owns retry/repair limits; provider transports have no internal retries.
- `MAX_RUN_SECONDS`, `MAX_CONCURRENT_RUNS`: positive limits. One case may have
  only one active run (409); the global concurrency limit returns 429.

Restart marks persisted queued/running runs failed with `run_interrupted`;
graceful shutdown cancels tasks and records interruption. Retry creates a new
run. Cases, evidence, snapshots and immutable report versions survive restart.
Versions are allocated in one SQLite write transaction.

Configure optional `MAX_RUN_COST_USD` and provider prices after checking current
pricing. Without usable prices/token usage, cost is `null`/unavailable, not zero,
and the cost limit cannot be enforced. This is an approximate limit checked
before calls, not a guaranteed spending cap for concurrent/in-flight requests.
Wall-clock time and bounded retries still apply.

## Mentor API connection

The team wallet's supplied instructions specify an OpenAI-compatible **Chat
Completions** gateway, bearer team key and `max_completion_tokens`. This adapter
does not use Responses, embeddings, images, audio, web search or multiple choices.
It makes non-streaming requests; the website continues polling background runs.

Set these on the Railway **api** service, or in `services/api/.env` for local work:

```dotenv
LLM_PROVIDER=openai
LLM_BASE_URL=https://secrethon-gateway.nicewave-ab4e0867.swedencentral.azurecontainerapps.io/v1
LLM_MODEL=gpt-6-luna
LLM_API_KEY=replace-with-your-team-key
```

`LLM_BASE_URL` is the base ending in `/v1`, not the `/chat/completions` URL.
The adapter appends that route, sends `Authorization: Bearer`, and uses the
existing JSON schema validation, bounded repairs/retries and token tracing.
Missing token usage stays unavailable; configure prices only from verified
wallet/provider information. Errors never expose raw provider bodies or keys.
HTTPS is required outside localhost, and redirects are refused.

The team key is separate from `API_SHARED_SECRET` (web-to-Python authentication).
Do not add the team key to the **web** service, browser code or Git. No changes
to R3/R4/R5 agents are needed; they use the shared adapter.

From `services/api`, run `python scripts/check_llm.py` for **one paid request**,
with at most 256 completion tokens, a 30-second timeout and no automatic retry.
It reports connectivity and token usage without printing the key or response
text. This check does not create a case/report or require the committee chair.
It does not verify analysis quality or close #7. Redeploy the API after merging
the provider code and setting its variables; a key alone cannot update code.

For a real committee run, use `DEV_STUBS=false` and integrate every required
module, including `synthesize_committee`. Until then, a successful connectivity
check is still only an isolated model call.

Request format reference: [OpenAI Chat Completions](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create).
The gateway URL/model above come from the team's wallet connection instructions.

## Pipeline and validation

validate → retrieve → science/translation/market → clinical → investment →
audit (one subject repair) → chair (one completeness repair) → audit new chair
claims → validated report. Modules are discovered from `vic.evidence` and
`vic.agents`; missing required functions fail with `module_not_ready`.

R2 sends subject/chair repair feedback through the shared structured adapter.
Malformed output gets bounded schema repairs. Provider/source failures,
timeouts, invalid evidence links and conflicting IDs cannot become completed
reports. All 11 sections and 5–10 diligence questions are required; specialist
risk records are retained alongside chair risks. Persistently blocked claims
become unverified; unresolved critical claims cannot support Invest.
R3's audit is heuristic and does not establish clinical or financial accuracy.

`evidence_only` skips external retrieval and uses evidence added to the case.
An empty evidence-only case is refused. New runs for an existing report require
`parent_report_id`; old reports remain unchanged. Full reruns create new snapshots
and revisions. Text upload uses one excerpt; the PDF route still returns 501
after type/size validation (R2-03).

## Modes and verification

- `DEV_STUBS=true`: all modules are synthetic. Reports/warnings explicitly say so;
  real evidence is refused when any stub is active.
- `DEV_STUBS=true` plus `STUB_MODULES=build_evidence_pack,audit_claims,analyze_investment,synthesize_committee`:
  exercises R4/market agents with R3 synthetic fixtures and real model calls.
  This partial synthetic mode does not complete #7.
- `DEV_STUBS=false`: all required modules must exist; no fallback to stubs.
- `RUN_BACKEND=mock`: legacy immediate fixture responses for development only,
  with `X-VIC-Mock: true`. Production refuses this mode.

Commands from `services/api`:

| Purpose | Command |
| --- | --- |
| Tests | `pytest -q` |
| Module/prompt readiness | `python scripts/check_wiring.py` |
| Stored trace | `python scripts/show_trace.py RUN_ID` |
| OpenAPI export | `python scripts/export_openapi.py` |
| Fixtures | `python scripts/generate_fixtures.py` |
| Fixture validation | `python scripts/validate_fixtures.py` |

Trace contains model/prompt/config versions, module origins, snapshot ID,
usage, stage durations and warnings, with configured secrets redacted. It is
persisted before terminal run status becomes visible. Trace output uses UTF-8
on Windows as well as Unix.

Before closing #7, integrate the real R5 chair, run with `DEV_STUBS=false`, and
record an HTTP run using real provider calls, a persisted validated report
and trace. Test synthetic/evidence-only input, outage, malformed output,
timeout and restart; record model/prompt/config/snapshot IDs and cost
availability. No live verification was performed by this PR review.

R3/R4/R5 use `vic.contracts`, `vic.run_context.RunContext` and
`vic.llm.generate_structured`; R2 does not edit their domain code or prompts.
