# R5 — Failure Miner: handoff

Реалізація на `codex/r5-failure-miner`, початкова база `origin/main` 7be159f;
9 жовтня 2026 оновлено через fast-forward до ffa8380 без конфліктів.
Commit/push/merge не виконуються в межах цієї роботи.

## Призначення

Критичний опонент збирає матеріальні ризики та можливі провали з науки,
перенесення на людину, клініки, ринку, фінансів, партнерств і патентів.
Кожен провал має ланцюжок: проблема → на що впливає → можливий наслідок →
вплив на інвестицію → наступна перевірка. Повертає взаємозв'язки ризиків,
пріоритети з поясненням, докази/припущення/невідомості та ранжовані перевірки.
Факти, гіпотези й невідомості оцінюються окремо для кожної ланки.

## Виклик

```python
from vic.agents.business.failure_miner import analyze_failure_miner

result = await analyze_failure_miner(
    case, pack, ctx,
    science=science_result,
    translation=translation_result,
    clinical=clinical_result,
    market=market_result,
    investment=investment_result,
    partnerships=partnerships_result,
    ip_licensing=ip_result,
    investment_threshold=threshold_result,  # необов'язковий додатковий контекст
)
```

`case`, `pack`, `ctx` обов'язкові. Усі вісім upstream-входів необов'язкові:
RoleResult, JSON-словник RoleResult або None. R4 — три окремі входи.
Навіть відсутній контекст має domain_review з unknown і конкретною перевіркою.
Відсутність даних не є експериментальним провалом.

## Рух даних

1. `prepare_failure_inputs` перевіряє pack, scope, snapshot, run date,
   ролі, claims, upstream risk/section links, вкладені evidence IDs і snapshot.
2. Повні upstream результати, джерела й уривки доказів передаються в payload.
   Фінансові плани, calculated_financials, sensitivity, limitations,
   change_conditions і unknowns не обрізаються. Входи не змінюються.
3. Один виклик `ctx.model.generate_structured("failure_miner", payload,
   FailureAnalysis, ctx)`; внутрішні retries/repairs adapter можливі.
4. Pydantic перевіряє schema; `validate_failure_result` перевіряє посилання,
   basis, domains, origins, disposition кожного upstream ризику, граф і питання.
5. Python створює shared Risk для кожного FailureMode; ці записи не генеруються
   незалежно другою LLM, тому ID/priority/impact/check узгоджені з повною картою.
6. Python збирає unknowns, включно з вкладеними upstream unknowns, відсутніми
   ролями/датою, та запити доказів для пріоритетних перевірок.
7. Повертається RoleResult(role_id="failure_miner") з section key="key_risks".

## Вихід

```python
data = result.section_content[0].structured_data["failure_miner"]
data["failure_modes"]
data["domain_reviews"]
data["interactions"]
data["diligence_priorities"]
data["upstream_context"]
result.claims
result.risks
result.unknowns  # == data["source_requests"]
```

Карта також містить prompt_version, snapshot_id, as_of_date, synthetic,
context_availability, claim_evidence_links і evidence_source_links.
`data["unknowns"]` зберігає первинний список моделі; `source_requests` —
об'єднаний список. Ранжовані питання мають rank, priority, rationale, failure_ids,
interaction_ids та повний check. Check містить question, method, evidence_needed,
uncertainty_reduced, decision_if_positive, decision_if_negative, inconclusive_if.

Для кожного upstream Risk рівно один disposition: included з конкретним
FailureMode й origin або deferred з обґрунтуванням. Повний оригінальний ризик
залишається в upstream_context незалежно від disposition. Рішення deferred
потребує змістовного review; Python не доводить його правильність.

## Сумісність і підключення R2

Shared contracts, llm.py, Modules/discovery, pipeline, Report builder, OpenAPI,
frontend та R3/R4 не змінені. Prompt завантажується за іменем файла через fallback
load_prompt; alias не потрібний. Adapter передає audit feedback через
ctx.feedback["failure_miner"] і записує content hash prompt у trace.
PROMPT_VERSION 1.0.0 — оголошена версія інструкції, не hash adapter.

Поточний Modules/pipeline ще НЕ викликає failure_miner. R2 має додати виклик після
потрібних upstream результатів, включити його claims в audit і його RoleResult у
список, переданий chair та build_report. Окремого results/r4 параметра тут немає.
Не заявляти про готовий API → pipeline → failure_miner запуск.

Поточний Report builder збирає canonical Risk у report.risks та ID у верхній
секції key_risks. Повні ланцюжки, взаємозв'язки й ранжовані питання зберігаються в
report.roles[...].section_content[0].structured_data["failure_miner"]. Builder не
переносить ці поля автоматично у верхню секцію або committee.diligence_questions.
Chair/R2 мають використати карту для фінальних питань; UI має читати карту ролі,
якщо потрібне відображення повного графа. Ця робота не змінює їхній код.

## Межі перевірки

Python підтверджує форму, охоплення upstream Risk і цілісність посилань;
не підтверджує істинність тексту, причинність, економічну значущість або патентний
висновок. Documented — supported claim із наявним evidence, не гарантія істинності.
R3 audit і фахова R4/фінансова/партнерська/IP перевірка залишаються потрібними.
Вузол не рахує нові фінанси, не виконує retrieval і не ухвалює фінальне рішення.

## Перевірки

Фінальна перевірка: 121 тест Failure Miner і 854 backend-тести пройшли.
Повний набір пройшов із системним дозволом для локальних сокетів.

Офлайн тести перевіряють повний ланцюжок, interactions, факти/гіпотези/unknown,
ранжування, всі входи як RoleResult та dict, відсутній evidence, namespace/scope,
посилання, dispositions, вкладені фінансові unknowns, незмінність входів,
реальний StructuredLlm/prompt/schema/feedback/trace, R3 audit та canonical Report.
Використовуються існуючі приклади Investment, Partnerships та IP Licensing.
Додатково перевірено новий OpenAICompatibleProvider R2 через httpx.MockTransport:
повні upstream-входи, prompt/schema, audit feedback, результат і trace usage.
Live LLM/API не запускались.

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=services/api/src /private/tmp/r5-ip-licensing-venv/bin/python -m pytest services/api/tests/vic/agents/business/test_failure_miner.py -q -p no:cacheprovider
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=services/api/src /private/tmp/r5-ip-licensing-venv/bin/python -m pytest services/api/tests -q -p no:cacheprovider
```

Повний набір потребує дозволу для локальних сокетів двох deployment-тестів.
