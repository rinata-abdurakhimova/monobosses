# Журнал помилок evaluation R5

Статус: порожній шаблон · Підготовлено 2026-10-09 · Власниця: R5 (Uliana).

Записів оцінювання відповідей цього dataset ще немає. Порожній журнал не доводить,
що система не помиляється. Наявні офлайн-перевірки описані окремо в
[validation-results.json](validation-results.json).

## Реєстр

| ID | Case / run / split | Вид | Пункт rubric | Severity | Expected → actual | Доказ / місце output | Owner | Статус | Fix / повторна перевірка |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |

## Як заповнювати

Додаємо запис тільки після спостереженої помилки або предметного review.
Види: runtime_failure, unsupported_claim, critical_omission, financial_error,
decision_error, revision_error, leakage, expectation_defect.

- Severity: critical, major або minor за [чеклістом](rubric.md).
- Статус: open → in_progress → ready_for_review → resolved; deferred має причину.
  Відкритий critical дефект блокує прийняття evaluation навіть якщо його відкладено.
- Owner: R2 — runtime; R3 — evidence/leakage; R4 — science/clinical;
  R5 — business/finances/decision. Для юридичної істинності потрібен фахівець.
- Expected описує вимогу конкретного case; actual — спостережений результат.
  Додаємо claim/evidence IDs і шлях до report/trace, без API-ключів.
- Runtime-збій не оголошуємо доказом поганої семантики відповіді, якої не отримали.
- Початковий запис і невдалу спробу не стираємо після fix; додаємо новий run ID.
- Після fix повторюємо affected development cases. Зміни на основі holdout означають,
  що цей набір більше не є незалежною фінальною оцінкою.

## Форма детального запису

Копіювати після появи фактичного дефекту; зараз це лише перелік полів:

```text
ID:
Case / family / split:
Run / attempt / config / expectations version:
Вид / severity / rubric IDs:
Expected:
Actual:
Report/trace path та output location:
Claim / evidence / source IDs:
Вплив на рішення:
Owner / reviewer:
Статус:
Fix / commit або hash змінених файлів:
Повторна development-перевірка / run ID / результат:
Залишкові обмеження:
```

Узгодження expectations до запусків ведемо в
[expectations-review.md](expectations-review.md). Підсумки фактичного evaluation — у
[звіті](../docs/evaluation-report.md).
