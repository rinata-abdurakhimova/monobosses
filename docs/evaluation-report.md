# Evaluation R5 — структура майбутнього звіту

**Статус: DRAFT / NOT_RUN.** Підготовлено 2026-10-09.
Це структура для заповнення після запусків і людського review, а не звіт про
доведену якість LLM. Live-відповідей на цей dataset та їхніх оцінок тут немає.

## 1. Що оцінюємо

Сім business-вузлів R5: market, investment, failure_miner, investment_threshold,
partnerships, ip_licensing, chair; їхній внесок у фінальний Report і revisions.
Окремо зазначити node-level чи integrated pipeline runs, synthetic чи real cases.

Мета: перевірити підтримку фактів, повноту ризиків, чесність unknowns, фінансову
коректність, обґрунтованість рекомендації та реакцію на нові докази.
Не заявляти підтверджену прибутковість або відсутність галюцинацій на всіх запитах.

## 2. Підготовлені матеріали

| Матеріал | Поточний стан |
| --- | --- |
| [Rubric](../evals/rubric.md) | Версія 1.0.0, 55 правил |
| [Dataset](../evals/cases/manifest.json) | Версія 1.0.0, 21 synthetic case, 18 сімейств |
| Development / holdout | 13 / 8; споріднені variants в одному split |
| Expectations | Авторські; review R3/R4/R5 ще не зафіксовано |
| [Фіксація контенту](../evals/cases/dataset-lock.json) | Hashes dataset і code baseline; live model/config ще не заморожені |
| [Review tracker](../evals/expectations-review.md) | NOT_REVIEWED |
| [Журнал помилок](../evals/error-log.md) | Порожній шаблон |

### Вже виконані офлайн-перевірки

За збереженим [validation-results.json](../evals/validation-results.json), 2026-10-09:
21 case пройшов schema/import/provenance/retrieval checks; 8 numeric probes
перевірили 24 точні значення та 3 очікувані відхилення неправильних inputs;
Model calls у валідаторі: 0.

Після переходу Market на два паралельні виклики пройшли **984 backend-тести
та 11 evaluation-тестів — разом 995**. Попередні 970 backend-тестів були
результатом підготовки dataset до цієї зміни. Також пройшли 40 frontend-тестів,
TypeScript, перевірка frontend-контрактів і підключення вузлів та промптів.
Деталі й розміри синтетичних запитів: [Market handoff](r5-market-request-budget.md).
Це офлайн-перевірки; реальний mentor gateway після зміни ще не перевірений.
Ці результати не додаємо до метрик якості реальної LLM нижче.

## 3. Узгодження очікувань

Заповнити: reviewers, дата review, case IDs, знайдені неточності, виправлення,
погоджена версія expectations/rubric і нерозв'язані розбіжності.
Кожен PASS має reviewer і причину; N/A потребує предметного пояснення.
Юридичні висновки не видавати за погоджені фахівцем без такого review.

## 4. Конфігурація та відтворюваність запуску

Заповнити після фактичного запуску:

| Поле | Значення |
| --- | --- |
| Evaluation ID / дата і час із timezone | — |
| Code commit / hashes незакомічених змін | — |
| Dataset / rubric / expectations versions і hashes | — |
| Manifest path / split / node-level або integrated | — |
| Provider / model / відома версія | — |
| Prompt versions / hashes | — |
| Generation settings / retry / repair / budget limits | — |
| Runner version / команда запуску | — |
| Artifact directory / config / summary / reports / traces | — |
| Pricing source / currency / price date, якщо відомі | — |

API-ключі, секрети та `.env` не включати. Holdout config зафіксувати до запуску;
зазначити, чи були будь-які зміни після перегляду holdout outcomes.

## 5. Метод оцінювання

Python перевіряє структуру, посилання й точні числові умови.
R3 читає supporting excerpts; R4 оцінює scientific/clinical applicability;
R5 перевіряє фінанси, business і rationale; R2 — runtime/передачу даних.
LLM judge, якщо використаний, описати окремо як допоміжний інструмент.

Застосовуємо [rubric](../evals/rubric.md): PASS=2, PARTIAL=1, FAIL=0;
NOT_REVIEWED і обґрунтовані N/A видимі окремо. Критичний дефект не ховається
за середнім балом. Для запису review є [форма](../evals/review-template.json).

## 6. Результати по кейсах

Таблиця поки порожня: додавати лише фактичні run/review records.
Не змішувати успішне виконання pipeline з успішною оцінкою змісту.

| Case / family / split | Run / attempt | Runtime status | Recommendation | Semantic case status | Reviewed / applicable | Score | Critical defects | Reviewers / artifacts |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |

Case status: accepted, needs_revision, incomplete, run_failed або not_run.
Показувати всі заплановані cases і спроби, не лише найкращі чи completed runs.

## 7. Метрики

Усі значення наразі **не виміряні**. Знаменники й відсотки заповнюємо після run/review.
Для нульового знаменника метрика N/A; пропущений review не зараховуємо як PASS.

| Метрика | Як рахувати | Фактичний результат |
| --- | --- | --- |
| Accepted cases | Accepted / усі заплановані cases відповідного split | — |
| Execution outcomes | Completed, failed, not_run із точними counts | — |
| Підтримка фактів | Supported / усі reviewed substantive factual claims; поруч reviewed / усі claims | — |
| Critical omissions | Пропущені / усі очікувані critical items | — |
| Decision agreement | Допустиме й обґрунтоване рішення / усі cases, де очікується рішення | — |
| Review coverage | Reviewed / усі applicable rubric items | — |
| Case score | Сума балів / (2 × reviewed applicable items), із coverage поряд | — |
| Decisive revisions | Passed / усі planned decisive pairs | — |
| Irrelevant revisions | Passed / усі planned irrelevant pairs | — |
| Relevant non-decisive update | Змістовне оновлення критерію/аргументів без примусової зміни категорії | — |
| Runtime | Фактичні median/p95 latency, sample size і метод percentile | — |
| Tokens / cost | Фактичне usage/cost, включно з retries та failed attempts | — |

Dev і holdout звітуємо окремо; node-level та integrated результати теж окремо.
Невідомий cost не замінювати нулем; estimated cost явно позначати estimate.

## 8. Leakage та незалежність holdout

Заповнити: фактичні controls R3, dates/snapshots, expectations isolation,
identity mapping isolation, cutoff, blind guessing та залишкові limitations.
Поточні synthetic manifests мають partial; unseen або гарантовану незалежність
від training data не доведено. Невдале guessing не є гарантією.

Зафіксувати family split і відсутність tuning на holdout. Якщо holdout використали
для змін, позначити його regression set і підготувати новий незалежний набір.

## 9. Помилки, виправлення та повторні перевірки

Посилання на записи [error log](../evals/error-log.md), owners, severity, fixes,
affected dev reruns та відкриті critical defects. Початкові failures лишаються
в обліку; виправлений повторний run не стирає попереднього.

## 10. Gates і рішення про готовність

Поточний стан: **evaluation не завершене**.
Після run/review зафіксувати accepted / needs_revision / blocked / incomplete
за правилами rubric з причиною. Критичні дефекти блокують прийняття незалежно
від score. Закриття issues не випливає лише з офлайн-тестів.

## 11. Обмеження й наступні дії

Заповнити: обсяг вибірки, synthetic-only nature, неперевірені domains,
реальні provider/runtime обмеження, pending legal/scientific review та failures.
Поточний відомий live-блокер описано в [R2 handoff](r2-full-workflow-handoff.md);
нових live-спроб у межах підготовки цього звіту не виконували.
Не заявляти expert Unobio agreement без їхніх наданих labels.
