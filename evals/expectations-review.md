# Узгодження expectations — R3 / R4 / R5

Статус: PARTIAL_REVIEW · Dataset 1.0.1 · Оновлено 2026-10-09.
R3: 19 PASS на незмінених кейсах; 2 CHANGES_REQUESTED, правки внесено,
повторне погодження очікується. R4 і R5: NOT_REVIEWED.
[Джерело review та опис правок](r3-review-notes.md).

R3 перевіряє підтримку фактів, provenance і leakage; R4 — наукову/клінічну
достатність; R5 узгоджує business-висновки.

[Manifest](cases/manifest.json) · [Rubric](rubric.md).

## Реєстр

| Case | Split | R3 | R4 | R5 узгодження | Коментар / reviewer / дата / зміни |
| --- | --- | --- | --- | --- | --- |
| [dev-01-sparse](cases/dev-01-sparse/expectations.json) | development | PASS | NOT_REVIEWED | NOT_REVIEWED | Rinata / Codex, 2026-10-09; R3 PASS на snapshot e67b1f1; case unchanged |
| [dev-02-market-coverage](cases/dev-02-market-coverage/expectations.json) | development | PASS | NOT_REVIEWED | NOT_REVIEWED | Rinata / Codex, 2026-10-09; R3 PASS на snapshot e67b1f1; case unchanged |
| [dev-03-budget-unknown](cases/dev-03-budget-unknown/expectations.json) | development | PASS | NOT_REVIEWED | NOT_REVIEWED | Rinata / Codex, 2026-10-09; R3 PASS на snapshot e67b1f1; case unchanged |
| [dev-04-partial-budget](cases/dev-04-partial-budget/expectations.json) | development | PASS | NOT_REVIEWED | NOT_REVIEWED | Rinata / Codex, 2026-10-09; R3 PASS на snapshot e67b1f1; case unchanged |
| [dev-05-schedule-stress](cases/dev-05-schedule-stress/expectations.json) | development | PASS | NOT_REVIEWED | NOT_REVIEWED | Rinata / Codex, 2026-10-09; R3 PASS на snapshot e67b1f1; case unchanged |
| [dev-06-role-conflict](cases/dev-06-role-conflict/expectations.json) | development | CHANGES_REQUESTED | NOT_REVIEWED | NOT_REVIEWED | Rinata / Codex, 2026-10-09; правку внесено у 1.0.1, повторний R3 review pending |
| [dev-07-patent-barrier](cases/dev-07-patent-barrier/expectations.json) | development | PASS | NOT_REVIEWED | NOT_REVIEWED | Rinata / Codex, 2026-10-09; R3 PASS на snapshot e67b1f1; case unchanged |
| [dev-08-partner-fit](cases/dev-08-partner-fit/expectations.json) | development | PASS | NOT_REVIEWED | NOT_REVIEWED | Rinata / Codex, 2026-10-09; R3 PASS на snapshot e67b1f1; case unchanged |
| [dev-09-cross-domain](cases/dev-09-cross-domain/expectations.json) | development | PASS | NOT_REVIEWED | NOT_REVIEWED | Rinata / Codex, 2026-10-09; R3 PASS на snapshot e67b1f1; case unchanged |
| [dev-10-safety-before](cases/dev-10-safety-before/expectations.json) | development | PASS | NOT_REVIEWED | NOT_REVIEWED | Rinata / Codex, 2026-10-09; R3 PASS на snapshot e67b1f1; case unchanged |
| [dev-11-admin-after](cases/dev-11-admin-after/expectations.json) | development | PASS | NOT_REVIEWED | NOT_REVIEWED | Rinata / Codex, 2026-10-09; R3 PASS на snapshot e67b1f1; case unchanged |
| [dev-12-safety-after](cases/dev-12-safety-after/expectations.json) | development | PASS | NOT_REVIEWED | NOT_REVIEWED | Rinata / Codex, 2026-10-09; R3 PASS на snapshot e67b1f1; case unchanged |
| [dev-13-ready-research](cases/dev-13-ready-research/expectations.json) | development | PASS | NOT_REVIEWED | NOT_REVIEWED | Rinata / Codex, 2026-10-09; R3 PASS на snapshot e67b1f1; case unchanged |
| [hold-01-animal-human](cases/hold-01-animal-human/expectations.json) | holdout | CHANGES_REQUESTED | NOT_REVIEWED | NOT_REVIEWED | Rinata / Codex, 2026-10-09; правку внесено у 1.0.1, повторний R3 review pending |
| [hold-02-currency-price](cases/hold-02-currency-price/expectations.json) | holdout | PASS | NOT_REVIEWED | NOT_REVIEWED | Rinata / Codex, 2026-10-09; R3 PASS на snapshot e67b1f1; case unchanged |
| [hold-03-license-restriction](cases/hold-03-license-restriction/expectations.json) | holdout | PASS | NOT_REVIEWED | NOT_REVIEWED | Rinata / Codex, 2026-10-09; R3 PASS на snapshot e67b1f1; case unchanged |
| [hold-04-injection](cases/hold-04-injection/expectations.json) | holdout | PASS | NOT_REVIEWED | NOT_REVIEWED | Rinata / Codex, 2026-10-09; R3 PASS на snapshot e67b1f1; case unchanged |
| [hold-05-endpoint-gap](cases/hold-05-endpoint-gap/expectations.json) | holdout | PASS | NOT_REVIEWED | NOT_REVIEWED | Rinata / Codex, 2026-10-09; R3 PASS на snapshot e67b1f1; case unchanged |
| [hold-06-discontinued-unknown](cases/hold-06-discontinued-unknown/expectations.json) | holdout | PASS | NOT_REVIEWED | NOT_REVIEWED | Rinata / Codex, 2026-10-09; R3 PASS на snapshot e67b1f1; case unchanged |
| [hold-07-threshold-before](cases/hold-07-threshold-before/expectations.json) | holdout | PASS | NOT_REVIEWED | NOT_REVIEWED | Rinata / Codex, 2026-10-09; R3 PASS на snapshot e67b1f1; case unchanged |
| [hold-08-threshold-after](cases/hold-08-threshold-after/expectations.json) | holdout | PASS | NOT_REVIEWED | NOT_REVIEWED | Rinata / Codex, 2026-10-09; R3 PASS на snapshot e67b1f1; case unchanged |

## Як записати результат

Для кожного case: PASS, CHANGES_REQUESTED, N/A з предметною причиною або
NOT_REVIEWED. Це статус узгодження expectations, не оцінка model output.
PASS містить reviewer, дату та коротку підставу; R5 узгоджує спільний варіант,
а не замінює предметне погодження R3/R4. Нерозв'язану розбіжність лишаємо видимою.

Коментар до виправлення: case ID, файл/поле, що некоректно, що запропоновано,
відповідний уривок/метод/аргумент і важливість для рішення. Після погодження
змін R5 оновлює versions/hashes і повторює офлайн-валідатор. Зміна тексту документа
змінює source/evidence IDs; потрібно узгоджено оновити expectations references.

Перевірку ground truth робимо до holdout runs. Зміни після перегляду outcomes
фіксуємо окремо; не підлаштовуємо label заднім числом під відповідь моделі.
Ніяких LLM/API, model-output scoring або expert agreement цей tracker не підтверджує.
