# Спільний технічний контракт v1

Це стартова специфікація для реалізації, не опис уже працюючого API. Власник — R2. Вона створює відповідні Pydantic models, OpenAPI й JSON fixtures у R2-01. Всі ролі перевіряють свої поля до інтеграції. Вибір hosting/provider фіксуємо окремо після перевірки доступу та лімітів.

## 1. Структура і запуск

```text
apps/web/                         Next.js + TypeScript, R1
services/api/pyproject.toml        Python dependencies, R2
services/api/src/vic/              спільний Python package
  main.py                         FastAPI app, R2
  contracts.py                    Pydantic models, R2
  api/                            маршрути cases/runs/evidence/reports, R2
  storage.py                      SQLite repository для першої версії, R2
  llm.py                          один адаптер моделі, R2
  pipeline.py                     порядок викликів, R2
  evidence/                       R3
  agents/science/                  R4
  agents/business/                 R5
contracts/fixtures/                спільні JSON fixtures, R2 + R3
evals/                            case manifests/rubric/results, R5; runner R2
docs/                             документація, всі
```

SQLite — рекомендований мінімум для локального каркаса. Deployment потребує persistent volume або погодженого іншого сховища; тимчасовий диск не вважаємо збереженням reports.

R2 забезпечує встановлення API editable package і команду `python -m uvicorn vic.main:app --reload --port 8000` з каталогу `services/api`. R1 забезпечує `npm install` і `npm run dev` з `apps/web`. Остаточні версії dependencies та команди перевірити й записати в кореневий README під час реалізації. Рекомендовані Python dependencies: FastAPI, Pydantic, Uvicorn, HTTPX, pypdf, pytest та SDK обраної моделі.

### Display language

English is the default language of the interface and API-owned display text,
including generated report narratives, claims, role summaries, risks, diligence
questions, revision explanations, warnings, and error messages. Every shared
fixture in `contracts/fixtures/` must use English for all human-readable values,
including synthetic source titles/text, evidence excerpts, and case input.
Generate fixtures from `services/api/src/vic/synthetic.py`; do not translate only
the committed JSON or add a frontend-only translation that diverges from Python.

For synthetic sources, translate the source text and its excerpts together so
each excerpt remains an exact substring; recompute `content_hash` from the
English source text. Preserve IDs, enums, provenance, support status, scope,
recommendations, and the v1/v2 decision story. Existing saved reports are
snapshots and are not silently rewritten by a fixture-language update.

User input and real source quotations remain verbatim for provenance; do not
rewrite a quoted source to enforce the display language. Any translation of real
evidence must be identified separately from the original excerpt. This rule does
not require translating the team's internal documentation.

## 2. Мінімальні сутності

| Model | Поля та зміст |
| --- | --- |
| `CaseInput` | `indication`, `mechanism`, `scope` (`approach`/`program`), `program_data` (optional text), optional `modality`, `development_stage`, `as_of_date` |
| `Source` | `id`, `title`, `url` (nullable для private upload/synthetic), `type`, `published_at` (nullable), `retrieved_at`, `content_hash`, `synthetic`, optional `document_id` |
| `Evidence` | `id`, `source_id`, `excerpt`, `locator` (page/section/record field), `scope`, `limitations` |
| `EvidencePack` | `sources`, `evidence`, `retrieval_warnings`, `snapshot_id`, `synthetic` |
| `Claim` | `id`, `text`, `provenance` (`source`/`user`/`ai`), `support_status` (`supported`/`contradicted`/`mixed`/`unverified`/`unknown`), `evidence_ids`, `assumptions`, `scope`, `importance` (`critical`/`major`/`minor`) |
| `RoleResult` | `role_id`, `summary`, `position` (text), `claims`, `risks`, `unknowns`, `change_conditions`, `section_content` |
| `SectionContent` | `key`, `summary`, `claim_ids`, `limitations`, optional `structured_data` |
| `Risk` | `id`, `description`, `priority`, `claim_ids`, `impact`, `next_check` |
| `DiligenceQuestion` | `question`, `why_it_matters`, `evidence_needed`, `decision_if_positive`, `decision_if_negative` |
| `AuditFinding` | `claim_id`, `verdict`, `reason`, `evidence_ids`, `blocking` |
| `AuditResult` | `findings`, `unresolved_critical_claim_ids`, `warnings` |
| `Report` | `id`, `case_id`, `run_id`, `version`, `scope`, `synthetic`, `snapshot_id`, `recommendation`, `rationale`, `decision_conditions`, `sections`, `roles`, `claims`, `evidence`, `sources`, `disagreements`, `risks`, `diligence_questions`, optional `revision` |
| `Revision` | `parent_report_id`, `new_evidence_ids`, `changed_claims` (before/after), `previous_recommendation`, `new_recommendation`, `explanation` |
| `Run` | `id`, `case_id`, `status`, `stage`, `report_version` (nullable), `warnings`, `error` (nullable), `trace_id`, usage/latency/cost, model/prompt/config versions |

`recommendation` має лише `Invest`, `Conditional`, `Do Not Invest`. `unknown` не означає негативного експериментального результату. Якщо невідомий критичний факт блокує рішення, голова пояснює умови `Conditional`; його не перетворюємо на вигаданий факт.

Ключі 11 sections: `recommendation`, `scientific_thesis`, `human_translation_thesis`, `clinical_development_plan`, `competitive_landscape`, `commercial_opportunity`, `capital_to_milestone`, `key_risks`, `critical_unknowns`, `diligence_questions`, `sources`. Top-level recommendation/risks/questions та відповідні sections мають узгоджуватися; R2 робить одну канонічну збірку замість двох незалежних генерацій.

Ідентифікатори source/evidence незмінні в межах кейсу; claim IDs мають стабільний смисловий ключ, наприклад `science.target_validation`, щоб порівняти версії. Snapshot зберігає точні evidence IDs, уривки та hashes. Не порівнюємо reports лише за різницею довільного тексту.

Приклад для розробки, **повністю синтетичний, без реального препарату**:

```json
{
  "id": "translation.safe_exposure",
  "text": "The safety of the required human exposure has not been established.",
  "provenance": "ai",
  "support_status": "unknown",
  "evidence_ids": ["ev-synthetic-01"],
  "assumptions": [],
  "scope": "program",
  "importance": "critical"
}
```

Це приклад одного claim, а не повний fixture report. Повний report fixture створює R2, synthetic sources/evidence перевіряє R3, зміст перевіряють R4/R5.

## 3. API та помилки

| Метод і маршрут | Request | Response |
| --- | --- | --- |
| `GET /health` | — | `{"status":"ok"}`; readiness перевіряє сховище |
| `POST /cases` | `CaseInput` | HTTP 201, `{"case_id":"..."}` |
| `POST /cases/{case_id}/runs` | `{"mode":"live" або "evidence_only", "parent_report_id":null або ID}` | HTTP 202, `{"run_id":"..."}` |
| `GET /runs/{run_id}` | — | `Run` |
| `GET /cases/{case_id}/reports/{version}` | — | `Report` |
| `POST /cases/{case_id}/evidence` | JSON: `title`, `text`, optional `published_at`, `synthetic` | HTTP 201, `{"source_id":"...","evidence_ids":["..."]}` |
| `POST /cases/{case_id}/documents` | multipart: `file` (PDF), `title`, `synthetic` | Те саме; PDF extraction від R3 |

`scope=program` без достатніх program data повертає пояснений validation error або явне уточнення; не мовчки вигадуємо актив. `as_of_date` обмежує доступні докази; якщо дата доступності не встановлена, historical evaluation не допускає такий запис автоматично.

R2 визначає єдиний error envelope: `{"error":{"code":"...","message":"...","retryable":false}}`. Для request validation FastAPI 422 нормалізуємо до цього формату. Відсутній case/report — 404, несумісний parent report — 409, надто великий upload — 413, unsupported file — 415. UI не показує користувачу traceback, ключі API чи raw prompts.

Стани `Run.status`: `queued`, `running`, `completed`, `failed`. `stage`: `validate`, `retrieve`, `analyze`, `audit`, `synthesize`, `finalize`. `completed` тільки для report, який пройшов валідацію. Проміжні results не називаємо завершеною рекомендацією. Run виконується поза HTTP request lifecycle; для першого single-instance prototype можливий background task із явним recovery перерваних runs при restart. Durable queue — наступний крок за потреби.

## 4. Інтерфейс між Python-модулями

R2 визначає `RunContext`: case/run IDs, snapshot, as-of date, mode, model adapter, budget, trace collector. Логування й LLM calls тільки через цей контекст.

```python
# R3
async def build_evidence_pack(case: CaseInput, ctx: RunContext) -> EvidencePack: ...
async def import_document(document: UploadedDocument, ctx: RunContext) -> EvidencePack: ...
async def audit_claims(claims: list[Claim], pack: EvidencePack, ctx: RunContext) -> AuditResult: ...

# R4
async def analyze_science(case: CaseInput, pack: EvidencePack, ctx: RunContext) -> RoleResult: ...
async def analyze_translation(case: CaseInput, pack: EvidencePack, ctx: RunContext) -> RoleResult: ...
async def analyze_clinical(case: CaseInput, pack: EvidencePack, scientific_result: RoleResult, translation_result: RoleResult, ctx: RunContext) -> RoleResult: ...

# R5
async def analyze_market(case: CaseInput, pack: EvidencePack, ctx: RunContext) -> RoleResult: ...
async def analyze_investment(case: CaseInput, pack: EvidencePack, clinical: RoleResult, market: RoleResult, ctx: RunContext) -> RoleResult: ...
async def synthesize_committee(results: list[RoleResult], audit: AuditResult, ctx: RunContext) -> CommitteeDecision: ...
```

`CommitteeDecision` повертає recommendation, rationale, conditions, disagreements, risks, questions та додаткові claims. R2 збирає `Report`, R3 перевіряє нові claims голови перед finalization. Critical unsupported claim або провал валідації не дозволяє видати `completed`; після одного обмеженого repair повертаємо пояснену невизначеність/Conditional, якщо це коректно, або failed run.

Science/translation/market можуть виконуватись паралельно; clinical читає science/translation, investment читає clinical/market. Агенти не викликають один одного напряму — це робить pipeline R2. Evidence pack передається явно: власне відкриття браузера/пошук предметними agents обходить контроль provenance і заборонений у evidence-only mode.

## 5. Модель, конфігурація, збереження

- Adapter R2: `generate_structured(prompt_id, payload, response_model, ctx)`. Відповідь проходить Pydantic validation; retry на provider errors обмежений, repair invalid JSON також обмежений.
- Prompts зберігаються поряд з owner modules; записуються їх version/hash. IDs: science, translation, clinical, market, investment, chair, audit.
- Доповнення для [#28](https://github.com/rinata-abdurakhimova/monobosses/issues/28): погоджені R5 IDs — `market`, `investment`, `failure_miner`, `chair`, `investment_threshold`, `partnerships`, `ip_licensing`. Разом зі `science`, `translation`, `clinical`, `audit` це 11 експертних IDs. Нові IDs також використовуються для відповідних prompts після підключення R2; evaluation не є експертною роллю. Реєстрація ID у схемі не означає, що вузол уже реалізований або виконується.
- Результат кожної реалізованої перспективи — спільний `RoleResult`; `section_content` є списком `SectionContent`. Ролі й 11 report sections — різні сутності: додаткові ролі не створюють нових `SectionKey`. R2 зберігає claims/risks у канонічних списках Report, а R1 показує role-level claims, risks, unknowns і change_conditions із посиланнями claim → evidence → source. Майбутній невідомий ID можна показати нейтральною назвою у frontend; backend приймає лише погоджений enum.
- API env: `LLM_PROVIDER`, `LLM_MODEL`, `LLM_API_KEY`, `DATABASE_URL`, `CORS_ORIGINS`, `MAX_UPLOAD_BYTES`, `MAX_RUN_COST_USD`, `MAX_RUN_SECONDS`. Остаточні defaults задає R2 й документує; cost limit не застосовуємо за невідомого provider pricing як точну гарантію.
- Frontend використовує server-side API proxy із `API_BASE_URL`; polling теж через proxy. Browser не отримує LLM keys. Deployment proxy має право створювати тільки потрібні API requests.
- API production доступ захищається погодженим application auth або server-side shared secret, який перевіряє R2 й передає Next.js server; CORS не замінює auth. Rate limits і бюджети обмежують публічні запуски.
- На початку локальний SQLite; JSON reports/evidence snapshots можна зберігати як валідовані serialized objects. Версію виділяємо атомарно, щоб concurrent runs не отримали однаковий номер.
- Додавання evidence не змінює report. Rerun з parent_report_id створює нову версію; reports різних case IDs не можна зв’язати.
- Approximate cost рахуємо з фактичних tokens та перевірених ставок обраного provider із датою; якщо usage/rate недоступні, показуємо unavailable, а не 0. Evaluation фіксує ті самі параметри.

## 6. Мінімальні fixtures і перевірки

R2 створює `contracts/fixtures/case.json`, `evidence-pack.json`, `report-v1.json`, `report-v2.json`, `run-running.json`, `run-failed.json`. У synthetic before/after кейсі v1 — Conditional через відсутню безпечну експозицію; v2 — Do Not Invest через явний synthetic safety result. Це контрольована історія, не твердження про реальний механізм.

Перевірки: IDs існують; усі 11 sections присутні; questions 5–10; джерело відповідає excerpt; missing links не вигадані; v1 незмінний після v2; нерелевантний документ не змінює категорію без підстав. Fixtures спочатку використовуються всіма ролями; live cases оцінюємо окремо.

