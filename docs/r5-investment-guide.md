# Investment — workflow і фінансовий результат

Вузол поєднує план R4 з доказами R3, готує числові inputs і пояснює фінансовий
шлях. Працює у два виклики LLM з розрахунками Python між ними. Остаточну
рекомендацію комітету не приймає. Особисте докладне пояснення класів зберігається
окремо від репозиторію; цей файл — технічний guide актуального workflow.

## Входи

```python
await analyze_investment(case, pack, ctx,
    clinical=clinical_result, market=market_result,
    partnerships=partnerships_result, ip_licensing=ip_result)
```

case, pack, ctx обов'язкові. Усі чотири upstream-входи необов'язкові й
приймають спільний RoleResult або його JSON dict. Відсутність стає прогалиною.
Вузол не запускає інші вузли й не шукає джерела сам.

| Вхід | Використання |
|---|---|
| clinical | Milestone, потрібний результат, роботи, ресурси, залежності й ризики R4 |
| pack | Повні sources/evidence, цитати, одиниці та числові дані R3 |
| market | Сценарії можливості ринку, доступ, ціни, commercial_value, ризики й невідомості; це не дохід |
| partnerships | Формати, умови, ресурси та investment_implications; відповідність не є інтересом |
| ip_licensing | Права, обмеження, licensing options і прогалини; це не юридичний дозвіл |
| scenarios/stresses | Необов'язкові вже підготовлені caller-inputs; план зберігає їхні ID й не дублює їх |

## Послідовність

1. Python перевіряє case/pack/ctx і upstream links, snapshot та дати.
2. Перший виклик `investment_plan`, prompt 1.0.0, повертає PreparedInvestmentPlan.
   Він визначає роботи й збирає inputs із доказів; не пише фінансовий висновок.
3. Python звіряє точні цитати й числові токени, одиниці, валюту, застосування
   до робіт та структуру графіка. Створює числові об'єкти й виконує арифметику.
4. Другий виклик `investment`, prompt 2.0.0, повертає InvestmentExplanation:
   лише пояснення бюджету/часу, фінансових шляхів, наслідків і потрібних перевірок.
5. Python вставляє незмінні milestone/work/future-stage/stress-trigger записи
   в InvestmentAnalysis, перевіряє всю карту і збирає RoleResult.

Друга схема не містить полів для нового плану, stages, triggers, blueprints,
числових inputs чи розрахунків. Їх підміна через зайві поля відхиляється.
Планові claims/risks не можна повторити або переписати в другій відповіді.
Якщо друга модель бачить проблему плану, вона формулює перевірку/обмеження.
Невалідний перший етап зупиняє процес до другого виклику. Без автоматичних
повторних спроб усередині вузла; політика retries спільного адаптера — R2.

## Нові схеми підготовки

| Клас | Призначення | Поля |
|---|---|---|
| ScenarioBlueprint | Каркас числового плану; межі ще null, їх заповнює Python | id, name, milestone_id, horizon, currency, geography, as_of_date, assumptions, costs, cost_coverage, cost_unknowns, schedule, schedule_coverage, schedule_unknowns, allocated_asset_cash |
| StressBlueprint | Каркас додаткового ускладнення з посиланням на фіксований trigger | id, base_scenario_id, trigger_id, kind, assumptions, incremental_delay_days, incremental_cost, currency, cost_scale, burn_per_day, cost_coverage, unknowns |
| NumericOperand | Дослівні числові токени та одиниця з конкретного доказу | evidence_id, quote, minimum_text, maximum_text, unit, unit_text, currency |
| NumericBinding | Як застосувати operand до конкретного input без довільного коду | record_type, record_id, input_path, operation, operands, basis, applicability, assumptions, unknowns |
| FutureMilestone | Фіксований майбутній етап; фінансування пояснює другий виклик | milestone_id, stage |
| StressEvent | Фіксоване можливе ускладнення; відома затримка позначається вже врахованою | id, kind, trigger, work_ids, already_in_baseline, stress_ids |
| PreparedInvestmentPlan | Відповідь першого виклику: план і підготовлені inputs | claims, next_milestone, work_packages, future_milestones, stress_events, scenario_blueprints, stress_blueprints, numeric_bindings, risks, unknowns, limitations |
| FutureFundingExplanation | Фінансова інтерпретація відомого future milestone без нового stage | milestone_id, purpose, funding_need, possible_sources, prerequisites, scenario_ids, unknowns |
| StressExplanation | Наслідки відомого stress event без нового trigger/числових inputs | event_id, budget_effect, financing_effect, time_effect, unknowns, next_check |
| InvestmentExplanation | Відповідь другого виклику: фінансовий аналіз за готовими даними | summary, position, claims, capital, time, value_inflections, future_financing, financial_paths, stress_explanations, commercial_constraints, risks, unknowns, next_checks, change_conditions, limitations |

Основні NextMilestone/WorkPackage/Finding та фінансові класи збережено.
InvestmentAnalysis тепер збирає Python, а не повертає другий виклик LLM.

## Від цитати до числа

NumericBinding вказує точний target, наприклад `costs.study.amount` або
`schedule.study.duration_days`. Каркас містить null, а operand — дослівні
`minimum_text`, `maximum_text`, `unit_text` і quote з pack.

Приклад: цитата «USD 100-150 thousand» → токени 100/150, thousand, USD →
Python створює ReviewedRange з правильним масштабом. Якщо target — cash в
одиницях USD, отримаємо 100000–150000. LLM не рахує перетворення.

Дозволені лише copy одного source-operand або multiply кількості на ціну
за одиницю. Множення виконує Python; count і unit price мають рахувати той
самий тип предметів. Довільні формули, FX, probabilities, NPV/ROI та строки
отримання фінансування не обчислюються. Тривалості — у днях; неоднозначні
локальні формати чисел або інші одиниці залишаються прогалинами.

Якщо числових доказів немає, ranges залишаються null. Якщо немає потрібної
валюти/дати, можна повернути відсутній числовий сценарій із запитом на дані.
Один обґрунтований сценарій достатній; три назви не вимагають вигаданих чисел.

Прив'язки зберігаються як numeric_provenance із quote, tokens, unit, operation,
applicability, assumptions і resolved_range. Статус —
source_tokens_checked_semantic_review_pending. Це не автоматично підтверджений
кошторис: реальну підтримку числа, застосовність аналога й повноту перевіряє R3/людина.

## Арифметика Python

- Capital = сума development costs у звичайних одиницях валюти; diligence окремо.
- Finish роботи = max(finish її попередників) + duration_days; загальний час = max(finish).
- Funding gap = [max(capital.min − allocated_cash.max, 0), max(capital.max − allocated_cash.min, 0)].
- Stress increment = extra_cost × scale + incremental_delay_days × burn_per_day.

Allocated cash — лише кошти для цього активу й горизонту, не всі гроші компанії.
Partial/unknown кошторис дає відомий subtotal, але capital_to_milestone=null.
Аналогічно неповний графік не дає повного time. Decimal зберігає арифметику
без float; межі результатів — рядки. Діапазони групуються за milestone,
horizon, currency, geography, date; це не confidence intervals.

Затримка, вже включена в базовий план, не може бути числовим stress цього
плану. Можливе ускладнення потребує trigger і додаткових inputs; без чисел
залишається пояснений StressAssessment. Слабші результати можуть зупинити
програму, а не лише потребувати додаткових витрат. Семантична перевірка
подвійного підрахунку та реалістичності припущень залишається необхідною.

## Кінцевий результат і десять вимог

```python
result.section_content[0].structured_data["investment"]
```

Секція — capital_to_milestone, спільний RoleResult(role_id="investment").
Claims/risks містяться у RoleResult; sources/excerpts надходять із pack.
Повний upstream_context збережено, включно з market commercial constraints.
prepared_plan і fixed_plan_hash позначають зафіксовані описові записи;
calculated_financials містить inputs/results/formulas. Хеш не є аудитом.

| Вимога | Вихід |
|---|---|
| Наступний етап і конкретний результат | next_milestone |
| Роботи до нього | work_packages |
| Капітал, склад витрат, діапазон і припущення | capital, calculated_financials.scenarios та scenario_ranges |
| Час, залежності й затримки | time, schedule inputs, time_to_milestone_days |
| Події зміни оцінки | value_inflections |
| Подальше фінансування | future_financing, future_milestone scenarios |
| Власна розробка, ліцензування, придбання | три financial_paths |
| Наслідки з partnerships/IP | financial_consequences, retained obligations, financing_dependencies |
| Затримки, додаткові дослідження, слабші результати | три stress_assessments, optional stress_scenarios |
| Прогалини, питання й докази | unknowns/source_requests, next_checks, claims/evidence links, numeric_provenance |

## Перевірки та інтеграція

Синтетичні приклади містять обидві mock-відповіді і відтворюються без caller
сценаріїв. Тести перевіряють джерельні токени, шкали/одиниці, арифметику,
неповні дані, незмінність плану, відсутність дублювання відповідей, early failure,
upstream fixtures і ручний синтетичний Report. Live API не запускали.

R2 має зареєструвати/завантажити новий prompt ID investment_plan; investment
вже зареєстрований, але тепер має prompt 2.0.0. Адаптер/pipeline/Report builder
залишаються інтеграційними потребами. Спільні файли не змінені. Mock-тести
не доводять factual accuracy, юридичну істинність, live-готовність або захист
від hallucinations/prompt injection. Деталі — r5-investment-handoff.md.

Перевірено на актуальному main `3cca985` після регресійних виправлень: 514 backend-тестів пройшли, із них 205 для investment.

## Захист числового пояснення та знаків

Друга відповідь тепер містить лише якісний текст без числових literals.
`validate_explanation_numbers` викликається під час `assemble_investment_analysis`
і відхиляє цифри в усіх текстових областях відповіді. Числа залишаються у
`calculated_financials`; у тексті потрібно посилатися на структуровані сценарії.
Structured reference fields і назви команди R1–R5 дозволені. Це уникає також
перенесення справжнього числа до неправильного сценарію чи одиниці.
Лексичний guard не перевіряє числа словами або правдивість якісних тверджень.

Числові source tokens перевіряються на ASCII/Unicode мінуси, включно з
пробілами після знака. `USD −100` більше не може стати додатним `100`.
Позитивні діапазони `100–200` залишаються дозволеними. Перевірка знаків не
замінює семантичного аудиту фінансової цитати.
