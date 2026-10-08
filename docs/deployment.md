# Railway deployment — R1-04 / issue #18

Deploy both applications in one Railway project. The jury receives one HTTPS website URL. The website proxies requests to the private Python service; the browser never needs its internal address or model credentials. The PDF flow and 10 MiB file limit are retained.

This is deployment preparation. It does not complete #18: the backend still has in-memory storage, synthetic runs/revisions, PDF 501 and unfinished authentication. A volume and environment variable alone do not make the in-memory repository persistent.

## What Rinata does now

1. Create a [Railway account](https://railway.com/) and connect GitHub. Check whether the account has Full Trial network access; Limited Trial may prevent source/model calls. Do not upgrade or add paid resources just to prepare the project. Check remaining credits before the jury session.
2. Grant Railway access to `rinata-abdurakhimova/monobosses`.
3. Make these deployment changes available on the GitHub branch you will deploy. Local files are not available to Railway until committed and pushed.
4. Create one project with two services named **api** and **web**, both linked to that repository and the same branch. Configure each before starting its first deployment. Keep the source/root directory at the repository root, not `apps/web` or `services/api`: the website build needs the shared `contracts` directory.
5. In each service's Variables, set `RAILWAY_DOCKERFILE_PATH` to its Dockerfile below. In Settings, enter the corresponding health-check path, health-check timeout 300 seconds, and restart policy On Failure with at most 3 retries. Leave custom build/start commands unset; Docker handles them. Use dashboard settings for this new project: Railway's legacy `railway.json`/`railway.toml` deployment configuration is deprecated.

## Configure the API service

| Setting | Value |
| --- | --- |
| `RAILWAY_DOCKERFILE_PATH` | `deploy/railway/api.Dockerfile` |
| Port variable | `PORT=8000` |
| Health-check path | `/health` |
| Public domain | None — keep API private |
| Replicas | One |
| Serverless/sleep | Disabled for the jury test session |

The Docker command runs `python scripts/serve.py`. It creates an explicitly dual-stack socket so IPv4 health checks and IPv6 private-network traffic reach the same `PORT`, then runs Uvicorn with one worker without development reload. A plain `uvicorn --host ::` listener can be IPv6-only and prevent the hosting health check from reaching it. The package is installed from the copied source so prompt files remain beside their agent modules. The base image is Python 3.12.

Deploy and check Railway's API logs for startup and a successful `/health` check. That check confirms the service runs, not that a complete analysis is implemented.

For the final persistent deployment, attach a volume to **api** at `/data` and set `DATABASE_URL=sqlite:////data/vic.sqlite3`, after confirming this path with R2's repository implementation. Persistent disk uses resources/credits. Do not use multiple API replicas with this SQLite arrangement. R2 must configure storage of imported documents/snapshots on durable storage as well. Currently these settings have no effect on the in-memory repository.

Backend environment variables, once R2's implementation is ready:

| Variable | Where the value comes from |
| --- | --- |
| `LLM_PROVIDER`, `LLM_MODEL` | Provider/model agreed with R2 |
| `LLM_API_KEY` | Provider dashboard; enter only in Railway API variables |
| `DATABASE_URL` | Durable database path/connection agreed with R2 |
| `API_SHARED_SECRET` | Generated secret after the backend/header contract is implemented |
| `MAX_UPLOAD_BYTES` | `10485760` (10 MiB) |
| `MAX_RUN_SECONDS` | `600` unless R2 documents a different budget |
| `MAX_RUN_COST_USD` | Verified model-call spending budget; not a placeholder zero |
| `CORS_ORIGINS` | Public website origin if required by the backend; browsers use the website proxy |

Do not enter model keys yet for the synthetic preview: the current adapter does not use them. Setting `API_SHARED_SECRET` currently does not enforce authentication. Keep the API private, and finish the agreed authentication implementation before claiming #18's security criterion is satisfied.

## Configure the website service

| Setting | Value |
| --- | --- |
| `RAILWAY_DOCKERFILE_PATH` | `deploy/railway/web.Dockerfile` |
| Port variable | `PORT=3000` |
| `API_BASE_URL` | `http://api.railway.internal:8000` |
| Health-check path | `/api/health` |
| Public domain | Generate one on **web** only, target port 3000 |

Both services must be in the same Railway project environment. If the API service has another name, replace `api` in the internal address with its actual internal DNS name. The private URL is only usable from Railway, not from your laptop or a jury browser.

The website Dockerfile installs the pinned npm lockfile with Node 24, copies shared contracts, checks contract drift and builds Next.js. Its production command binds to `0.0.0.0` and uses `PORT`, overriding the local package script's loopback-only hostname. No secret is required during the build. Runtime model keys stay in Python.

After generating the public website domain, set **web** `WEB_ORIGIN` to exactly that HTTPS origin, e.g. `https://your-project.up.railway.app`, without a path or query, and redeploy the website. This allows same-origin writes when Railway forwards HTTPS traffic internally over HTTP. Cross-origin writes still fail; browser-supplied forwarding headers are not trusted. Update `WEB_ORIGIN` when adding a custom domain.

No provider key is needed on **web**. It needs `API_BASE_URL`, `WEB_ORIGIN` and eventually the agreed server API credential. Never use `NEXT_PUBLIC_` for those credentials. `/api/health` checks the website process only; it does not call the model or confirm Python readiness.

## Verify the deployed preview

1. Open the public website's `/api/health`: expect `{"status":"ok"}`.
2. Open `/cases/revision-sample?version=1` and `?version=2`; inspect an exact excerpt.
3. Create one synthetic assessment through the Python API flow. Confirm the report is labelled synthetic. Check that reloading uses GET requests and does not create a new run.
4. Import synthetic text. Confirm an explicit success message and no automatic review. Run one review, then independently open the parent version. The current backend allows one fixed v1 → v2 review per fresh case and ignores the imported evidence.
5. Submit a test PDF: currently expect readable 501. Reject oversized files. Verify a valid PDF near 10 MiB reaches the backend through Railway's proxy; do not infer this from localhost alone.
6. With Node 22.18+ on your laptop, from `apps/web` run `npm run test:api` and `npm run test:evidence-api` with `WEB_BASE_URL` set to the deployed website. Both checks make synthetic test records; they do not establish real analysis quality. The evidence smoke check deliberately expects the current mock/501 behavior and needs updating after R2 integrates the pipeline.

## Checks required before closing #18

- Real input → completed saved report, plus a failed run and a source outage.
- Readable PDF import; unreadable/unsupported/oversized PDF errors; private sources without fabricated public URLs.
- Safety and unrelated updates use actual imported evidence, with honest v1/v2 comparisons.
- Restart API, then reopen the previously created case/report and evidence. Current in-memory storage fails this check; attaching a volume is insufficient until R2 implements persistence.
- Confirm server authentication is enforced and secrets never appear in the browser bundle, URLs or logs.
- Jury can reach the public website while both services are running and hosting/model budgets remain available.

## Recovery and recorded release

Keep the deployed Git commit and service settings in the release notes. If the website returns 503, check `API_BASE_URL`/`WEB_ORIGIN`; for 502 check API deployment, internal DNS and both services' environment. A 403 on an ordinary form submission usually means `WEB_ORIGIN` does not match the public domain. A 501 PDF or 409 mock revision is a current backend limitation, not a missing Railway setting.

Use redeploy for a configuration change and rollback to a known compatible commit for a bad release. Back up persistent data before schema-changing releases; a code rollback does not restore database state. A volume-mounted service can have brief deployment downtime. Stop unused test services to conserve trial credits, after the jury testing period.

Release details (fill after deployment):

- Website URL: pending.
- Railway project and service names: pending.
- Deployed Git commit: pending.
- Persistence/auth/PDF/live-analysis checks: pending.

## Validation of this preparation

39 frontend tests pass, including the HTTPS-origin regression test. TypeScript, contract drift, formatting, production build and `git diff --check` pass. A local production server check confirms health/fixture HTTP 200, a configured HTTPS-origin submission HTTP 201 through Python, and a cross-origin submission HTTP 403. Docker image builds and Railway networking/volume behavior require Docker or an actual Railway deployment; Docker is not installed in this workspace, so those are not locally verified. No hosting account, paid resource or deployment is created by adding these files.

Platform references: [Railway monorepos](https://docs.railway.com/guides/deploying-a-monorepo), [Dockerfiles](https://docs.railway.com/builds/dockerfiles), [private networking](https://docs.railway.com/networking/private-networking), [health checks](https://docs.railway.com/deployments/healthchecks), [volumes](https://docs.railway.com/volumes), [trial](https://docs.railway.com/pricing/free-trial).
