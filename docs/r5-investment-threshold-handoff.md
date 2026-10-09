# R5 Investment Threshold — локальна реалізація

Вузол оцінює поріг обґрунтованості вкладення зараз і на наступному етапі.
Він не обчислює окупність і не ухвалює фінальне рішення комітету.

```python
await analyze_investment_threshold(case, pack, ctx,
    science=..., translation=..., clinical=..., market=...,
    partnerships=..., investment=..., ip_licensing=...)
```

Обов'язкові case/pack/ctx. Кожен upstream-вхід — RoleResult, його JSON-словник
або None. R4 передає science, translation та clinical. Відсутній контекст
передається як null із context_availability=false, а не замінюється вигадкою.
Зберігаються повні sections, фінансові результати, claims, risks і unknowns.

Рух даних: Python перевіряє pack, snapshot, дату аналізу, scope і посилання;
один виклик adapter.generate_structured повертає ThresholdAnalysis; Python
перевіряє локальні й upstream-посилання, повноту критеріїв/прогалин і статуси;
збирає RoleResult(role_id="investment_threshold").

Повний вихід:
`result.section_content[0].structured_data["investment_threshold"]`.
Секція — існуюча diligence_questions. Claims і risks залишаються окремо в
RoleResult, вкладені finding.claim_ids посилаються на ці локальні claims.
Метадані включають snapshot_id, as_of_date, synthetic, prompt_version,
context_availability, upstream_context, source_requests, claim_evidence_links
та evidence_source_links. Downstream отримує цей RoleResult через pipeline.

| Вимога | Поля |
| --- | --- |
| Результат для інвестиції зараз / далі | gates[].horizon, required_result |
| Етап отримання результату | obtainable_stage; gaps[].check.feasible_stage |
| Достатній результат і обґрунтування | criteria[].sufficient_result, rationale, assessment_method |
| Наявні докази | existing_evidence[] для кожного критерію, evidence_ids, limitations |
| Відстань між доказами й вимогою | gaps[].missing_result_or_data, criterion_ids |
| Вплив кожної прогалини | investment_impact, priority |
| Перевірка | check.method, evidence_needed, feasible_stage |
| Продовження / перегляд / зупинка | continue_if, revise_if, stop_if у gate і кожній перевірці; inconclusive_if |

Finding: documented потребує supported claims із доказами; hypothesis — явних
припущень та unverified/unknown claims; unknown — null і явних невідомих.
Наявність цитати сама по собі не доводить достатність результату.
met потребує документованого assessment, доказів для всіх критеріїв,
документованих dependencies та відсутності прогалин. not_met/partially_met
потребують документованого assessment спостережених результатів.
Відсутність даних означає unknown; усі unknown → insufficient_data.
Для кожного непідтвердженого критерію потрібна прогалина з перевіркою.
Історичні дати ринкових аналогів не прирівнюються до дати поточного аналізу.

Після оновлення до main `7b80cd0` завантажувач R2 вже знаходить prompt
investment_threshold за назвою файлу без зміни registry. Він записує hash
вмісту prompt у trace; наше prompt_version=1.0.0 — оголошена версія інструкції.
У main `a060c26` R2 вже підключила investment_threshold після upstream-вузлів;
офлайн-інтеграцію перевірено. Успішний повний live run ще не підтверджений.
Shared contracts, llm.py,
Report builder, R3/R4 та frontend залишено без змін.

Числова арифметика тут не потрібна: investment financials передаються повністю.
Prompt вимагає джерельних або явно гіпотетичних числових критеріїв із
припущеннями та фаховим підтвердженням. Python перевіряє структуру/посилання,
а не змістовну відповідність чисел тексту чи істинність критеріїв. R3/R4
перевіряють докази й наукову достатність; правила stop є рекомендаціями
для розгляду, а не автоматичною зупинкою проєкту.

Перевірки — офлайн, із mock adapter; live LLM/API не запускали.
Наведені нижче записи про відсутність commit/push описують історичний етап; вузол уже є в main.

Оновлення 8 жовтня: origin/main підтягнутий у codex/r5-investment-threshold
через fast-forward, без merge-коміту; локальні файли збережені. До тестів
додано три перевірки сумісності з реальним StructuredLlm R2 та офлайн provider:
реальний prompt і schema, повний payload/output усіх семи ролей, audit feedback,
trace version/usage та відхилення schema-valid, але неузгодженого met gate.
Зовнішні LLM/API не викликаються. Це історичний запис до інтеграції. Стан на 2026-10-09: R2 підключила вузол у main;
офлайн-інтеграція перевірена, live semantic quality залишається відкритою.
