# Задачі команди та порядок виконання

Тут збережено повні тексти 18 задач для GitHub Issues. Це локальні специфікації, не підтвердження публікації. Фактичні номери й URL після створення будуть у `github-issues.json`. Сталі коди R1-01 тощо використовуйте в PR та комунікації незалежно від GitHub номерів.

Спочатку прочитайте [старт для ролей](../roles/README.md) та [спільний контракт](../implementation-contract.md).

| Код | Роль | Задача | Залежності для завершення |
| --- | --- | --- | --- |
| R2-01 | R2 — Kateryna | [Створити Python API skeleton, contracts v1 та спільні fixtures](r2-01.md) | Старт |
| R1-01 | R1 — Rinata | [Зробити Next.js форму та сторінку звіту на synthetic fixture](r1-01.md) | R2-01 |
| R3-01 | R3 — Victoria | [Реалізувати text/PDF import та synthetic evidence pack](r3-01.md) | R2-01 |
| R4-01 | R4 — Arina | [Написати scientific і human translation agents](r4-01.md) | R2-01, R3-01 |
| R5-01 | R5 — Uliana | [Реалізувати competitive landscape та commercial analysis](r5-01.md) | R2-01, R3-01 |
| R2-02 | R2 — Kateryna | [Запустити background runs, спільний LLM adapter та повний pipeline](r2-02.md) | R2-01 |
| R1-02 | R1 — Rinata | [Підключити форму, polling і report до Python API](r1-02.md) | R1-01, R2-02 |
| R3-02 | R3 — Victoria | [Підключити live sources та пошук суперечливих доказів](r3-02.md) | R3-01 |
| R4-02 | R4 — Arina | [Реалізувати clinical plan та визначення наступного milestone](r4-02.md) | R4-01 |
| R5-02 | R5 — Uliana | [Реалізувати capital/time to milestone та фінансові сценарії](r5-02.md) | R5-01, R4-02 |
| R3-03 | R3 — Victoria | [Реалізувати аудит claim → evidence та leakage checks](r3-03.md) | R3-01, R4-01, R5-01 |
| R5-03 | R5 — Uliana | [Реалізувати голову комітету, risks та 5–10 diligence questions](r5-03.md) | R4-02, R5-02, R3-03 |
| R2-03 | R2 — Kateryna | [Додати evidence uploads, report revisions та evaluation runner](r2-03.md) | R2-02, R3-01 |
| R1-03 | R1 — Rinata | [Зробити evidence drill-down, upload та порівняння версій](r1-03.md) | R1-02, R2-03, R3-03, R5-03 |
| R4-03 | R4 — Arina | [Перевірити зміну science/clinical висновків і підготувати expectations](r4-03.md) | R4-02, R2-03 |
| R5-04 | R5 — Uliana | [Зібрати dataset, провести evaluation та оформити результати](r5-04.md) | R5-03, R2-03, R4-03, R3-03 |
| R1-04 | R1 — Rinata | [Розгорнути Next.js і Python та перевірити весь сценарій](r1-04.md) | R1-03, R2-03, R3-02 |
| TEAM-01 | Вся команда; R1 координує demo, R5 — quality gates | [Провести фінальну перевірку, demo та підготувати README](team-01.md) | R1-04, R5-04 |

## Як читати залежності

«Потребує R2-01» означає, що final integration спирається на її результат. Draft UI/prompts/synthetic texts можна готувати паралельно. R2-02 будує runtime на stubs, потім підключає готові предметні modules; це не причина чекати всі agents перед написанням pipeline. Для закриття R2-02 потрібен повний flow, а не тільки stubs.

## Порядок запуску

1. R2-01: contracts/fixtures. Інші одночасно готують UI, synthetic pack, prompts і rubric.
2. R1-01, R3-01, R4-01, R5-01 та R2-02 skeleton: перший наскрізний каркас.
3. R3-02, R4-02, R5-02, R3-03, R5-03: live evidence, clinical/financial outputs, аудит і рішення.
4. R1-02, R2-03, R1-03, R4-03, R5-04: інтеграція, revisions, оцінювання. API інтеграцію можна почати раніше на частково готовому runtime.
5. R1-04 і TEAM-01: deployment, release gates, нові запити та demo.

## Статуси

`Todo` → `In progress` → `Review` → `Done`. Blocker записати в issue із посиланням на залежність та конкретним відсутнім результатом. Issues не мають assignees до підтвердження GitHub usernames; людський розподіл уже вказаний у role guides.


