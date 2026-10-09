# Узгодження expectations — R3 / R4 / R5

Статус: NOT_REVIEWED · Dataset 1.0.0 · Підготовлено 2026-10-09.
Зараз це tracker завдань, не записи завершеного людського review.

R3 перевіряє підтримку фактів, provenance і leakage; R4 — наукову/клінічну
достатність; R5 узгоджує business-висновки.

[Manifest](cases/manifest.json) · [Rubric](rubric.md).

## Реєстр

| Case | Split | R3 | R4 | R5 узгодження | Коментар / reviewer / дата / зміни |
| --- | --- | --- | --- | --- | --- |
| [dev-01-sparse](cases/dev-01-sparse/expectations.json) | development | NOT_REVIEWED | NOT_REVIEWED | NOT_REVIEWED | — |
| [dev-02-market-coverage](cases/dev-02-market-coverage/expectations.json) | development | NOT_REVIEWED | NOT_REVIEWED | NOT_REVIEWED | — |
| [dev-03-budget-unknown](cases/dev-03-budget-unknown/expectations.json) | development | NOT_REVIEWED | NOT_REVIEWED | NOT_REVIEWED | — |
| [dev-04-partial-budget](cases/dev-04-partial-budget/expectations.json) | development | NOT_REVIEWED | NOT_REVIEWED | NOT_REVIEWED | — |
| [dev-05-schedule-stress](cases/dev-05-schedule-stress/expectations.json) | development | NOT_REVIEWED | NOT_REVIEWED | NOT_REVIEWED | — |
| [dev-06-role-conflict](cases/dev-06-role-conflict/expectations.json) | development | NOT_REVIEWED | NOT_REVIEWED | NOT_REVIEWED | — |
| [dev-07-patent-barrier](cases/dev-07-patent-barrier/expectations.json) | development | NOT_REVIEWED | NOT_REVIEWED | NOT_REVIEWED | — |
| [dev-08-partner-fit](cases/dev-08-partner-fit/expectations.json) | development | NOT_REVIEWED | NOT_REVIEWED | NOT_REVIEWED | — |
| [dev-09-cross-domain](cases/dev-09-cross-domain/expectations.json) | development | NOT_REVIEWED | NOT_REVIEWED | NOT_REVIEWED | — |
| [dev-10-safety-before](cases/dev-10-safety-before/expectations.json) | development | NOT_REVIEWED | NOT_REVIEWED | NOT_REVIEWED | — |
| [dev-11-admin-after](cases/dev-11-admin-after/expectations.json) | development | NOT_REVIEWED | NOT_REVIEWED | NOT_REVIEWED | — |
| [dev-12-safety-after](cases/dev-12-safety-after/expectations.json) | development | NOT_REVIEWED | NOT_REVIEWED | NOT_REVIEWED | — |
| [dev-13-ready-research](cases/dev-13-ready-research/expectations.json) | development | NOT_REVIEWED | NOT_REVIEWED | NOT_REVIEWED | — |
| [hold-01-animal-human](cases/hold-01-animal-human/expectations.json) | holdout | NOT_REVIEWED | NOT_REVIEWED | NOT_REVIEWED | — |
| [hold-02-currency-price](cases/hold-02-currency-price/expectations.json) | holdout | NOT_REVIEWED | NOT_REVIEWED | NOT_REVIEWED | — |
| [hold-03-license-restriction](cases/hold-03-license-restriction/expectations.json) | holdout | NOT_REVIEWED | NOT_REVIEWED | NOT_REVIEWED | — |
| [hold-04-injection](cases/hold-04-injection/expectations.json) | holdout | NOT_REVIEWED | NOT_REVIEWED | NOT_REVIEWED | — |
| [hold-05-endpoint-gap](cases/hold-05-endpoint-gap/expectations.json) | holdout | NOT_REVIEWED | NOT_REVIEWED | NOT_REVIEWED | — |
| [hold-06-discontinued-unknown](cases/hold-06-discontinued-unknown/expectations.json) | holdout | NOT_REVIEWED | NOT_REVIEWED | NOT_REVIEWED | — |
| [hold-07-threshold-before](cases/hold-07-threshold-before/expectations.json) | holdout | NOT_REVIEWED | NOT_REVIEWED | NOT_REVIEWED | — |
| [hold-08-threshold-after](cases/hold-08-threshold-after/expectations.json) | holdout | NOT_REVIEWED | NOT_REVIEWED | NOT_REVIEWED | — |

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
