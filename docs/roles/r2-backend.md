# R2 — Kateryna: Python API та виконання agent flow

## Твій результат простими словами

Ти робиш центральну систему: вона приймає input, запускає потрібні модулі у правильному порядку й зберігає результат. Ти не пишеш за інших весь науковий аналіз; ти даєш їм спільні структури, LLM adapter і робочий спосіб підключити їхні функції.

Прочитай [спільний старт](README.md). Твоя перша задача R2-01 блокує інтеграцію інших, тому contracts та fixture віддай рано. Послідовність: R2-01 → R2-02 → R2-03.

## Що ти пишеш

У `services/api/src/vic`: `contracts.py`, `main.py`, `api/`, `storage.py`, `llm.py`, `pipeline.py`, `run_context.py`, `report_builder.py`; також `pyproject.toml`, `.env.example`, tests, OpenAPI export та `evals/run.py`. [Технічний контракт](../implementation-contract.md) задає спільні поля та signatures.

## Крок 1. Contracts, fixtures та API skeleton — R2-01

1. Створи встановлюваний Python package `vic`, FastAPI app і GET health. В `.env.example` лише назви та безпечні placeholders, без справжніх keys.
2. Реалізуй Pydantic models зі спільного контракту. Зроби enum statuses, recommendation і section keys; forbidden/dangling IDs виявляй перед завершенням report.
3. Узгодь поля з R1/R3/R4/R5: R1 — rendering, R3 — provenance, R4/R5 — role outputs. Зафіксуй зміни contract v1 до підключення їхніх модулів.
4. Створи synthetic `case.json`, `evidence-pack.json`, `report-v1.json`, `report-v2.json` і run state fixtures. Report містить усі 11 sections, 5–10 questions та working IDs. R3/R4/R5 перевіряють свої частини.
5. Реалізуй routes контракту спочатку на repository layer/mock handlers; не називай mocked analysis реальним run.
6. Export OpenAPI в `contracts/openapi.json`, додай install/run commands у README. Передай R1 fixture й endpoint examples; R3/R4/R5 — imports і signatures.

**Перевір:** fixture проходить validation; invalid indication повертає 422 envelope; невідомий case — 404; `pip install -e .` і documented start command працюють. Це результат першого PR.

## Крок 2. Справжній run та orchestration — R2-02

1. Реалізуй SQLite repository за abstraction: create_case, create_run, update_run, save_snapshot, save_report, get_report. Збереження version atomic; report після збереження незмінний.
2. POST run повертає 202 одразу. Background execution має явні states/stages, timeout і recovery: після restart перерваний run стає failed із поясненням, не висить running назавжди.
3. Створи один `generate_structured` adapter з model/prompt version, schema validation, обмеженими retries та usage tracking. Не зберігай secrets у trace.
4. Pipeline: validate → evidence R3 → science/translation/market → clinical → investment → audit → chair → final audit/validation → report. Застосуй signatures контракту.
5. Поки чужий модуль не готовий, підключи stub із явним `synthetic`/mock mode лише для development. Для completed live report усі необхідні компоненти мають працювати реально.
6. Валідуй claims IDs, sections, questions і scope. Якщо audit блокує критичний claim, зроби максимум один предметний repair; далі чесно познач unknown/Conditional, якщо коректно, або failed.
7. Оброби source outage, provider timeout, malformed model output і budget limit. Trace містить stage durations, usage, snapshots і config; приблизна cost недоступна → null/unavailable.
8. Додай production entrypoint, storage requirements, allowed origins, server API authentication і run limits; передай R1.

**Перевір:** через HTTP один synthetic/evidence-only input проходить реальні model calls і зберігається; source failure не виглядає як підтверджена відсутність даних; malformed output не стає completed report.

## Крок 3. Evidence uploads, revisions та evaluation runner — R2-03

1. Підключи text import і PDF parser R3. Обмеж file size/type; перевір parsing errors. Source/evidence зберігаються до запуску аналізу.
2. New evidence не переписує report. POST run з parent_report_id перевіряє належність case і створює новий snapshot та report version.
3. Для MVP виконуй повний rerun; не починай зі складного selective invalidation.
4. Порівняй stable claim keys, before/after recommendation і rationale. Revision output має посилатися на нові evidence IDs, а не просто казати «дані оновились».
5. Реалізуй `evals/run.py`: прочитати manifest → виконати pipeline → записати per-case report/trace/usage/config → створити summary. Рубрику та expectations надає R5; science labels перевіряє R4.
6. Evidence-only mode не використовує network retrieval; loader для blind cases не передає evaluator-only identity mapping у model payload.
7. Перевір concurrent runs, reload, failed upload та wrong parent ID. Передай R1 endpoints revisions, R5 runner commands.

**Готово:** v1 залишається незмінним після v2; revisions пояснюють змінені claims; runner може повторно запустити набір і зберегти фактичні результати.

## Кому передаєш що

- R1: OpenAPI, fixtures, API URL, start/deploy commands, env names, errors.
- R3: models Source/Evidence/Claim, storage functions і retrieval/audit hooks.
- R4/R5: models, RunContext, LLM adapter та bounded execution.
- Вся команда: reproducible README, architecture і traces без secrets.

## Не роби

Не створюй власний scientific prompt у pipeline замість модуля R4; не визначай recommendation кількістю голосів; не повертай raw LLM text як Report. Не перетворюй transient storage або in-process task на обіцянку production durability.

## Твої GitHub Issues

- [R2-01: #2](https://github.com/rinata-abdurakhimova/monobosses/issues/2) — Створити Python API skeleton, contracts v1 та спільні fixtures.
- [R2-02: #7](https://github.com/rinata-abdurakhimova/monobosses/issues/7) — Запустити background runs, спільний LLM adapter та повний pipeline.
- [R2-03: #14](https://github.com/rinata-abdurakhimova/monobosses/issues/14) — Додати evidence uploads, report revisions та evaluation runner.
