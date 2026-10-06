# [TEAM-01] Провести фінальну перевірку, demo та підготувати README

**GitHub issue:** [#19](https://github.com/rinata-abdurakhimova/monobosses/issues/19)

**Відповідальна роль:** Вся команда; R1 координує demo, R5 — quality gates. GitHub assignee призначає команда.

**Етап:** E. **Залежності для завершення:** [R1-04](r1-04.md), [R5-04](r5-04.md)

[Спільний порядок роботи](../roles/README.md) · [Спільний контракт](../implementation-contract.md) · [Загальний план](../../team-work-instructions.md)

## Результат

Продукт працює на двох різних cases і новому запиті; demo показує реальну зміну висновку та reproducibility.

## Код і файли

README.md; docs/architecture.md; docs/demo-script.md; docs/evaluation-report.md; docs/deployment.md

Це очікувані шляхи реалізації; на момент планування код ще не створено. Використовуємо один package `vic`, contracts і LLM adapter R2.

## Що за чим робити

1. R1/R2: перевірити deployment flow, commands/env/versioned reports/traces і source links.
2. R3/R4/R5: вибрати дві різні indication × mechanism з перевіреними даними; synthetic матеріали позначені.
3. Показати recommendation → claim → excerpt, потім decisive new evidence → rerun → changed conclusion із before/after.
4. Ввести holdout input поза двома demo cases; той самий pipeline, жодних name-based hardcoded answers.
5. R5: звірити release gates/error log; critical unsupported safety facts блокують release.
6. README: architecture, setup, model/API usage, source attribution, approximate per-run cost, traces, evaluation/deployment links.
7. Записати backup snapshot mode із явним label; не видавати його за live новий запит.

## Критерії готовності

- [ ] Два різні cases та незнайомий input працюють одним pipeline.
- [ ] Щонайменше один decisive update змінює conclusion; irrelevant update не форсує зміну.
- [ ] 11 report sections і evidence path присутні.
- [ ] Evaluation report/gates і limitations відкриті; critical defects усунені.
- [ ] README достатній іншій учасниці для запуску й пояснення demo.

## Як перевірити

Повна репетиція з іншою учасницею за demo script; повторити кейс за saved config/snapshot і переглянути trace.

## Що передати команді

Команда готова показати систему та пояснити evidence, quality controls і limitations.

У PR: посилання на цю задачу, опис working behavior, commands/input/result перевірки та відомі обмеження. Не закривати live-задачу лише на mock output. API/schema change погодити з R2 і споживачами.
