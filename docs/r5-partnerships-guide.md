# Partnerships: пояснення вузла

Це локальна реалізація R5, prompt 1.0.0. Вона не шукає партнерів у мережі,
не пише компаніям і не встановлює їхню готовність до угоди. Вона аналізує
надані докази та повертає кандидатів або категорії з умовами й перевірками.

## Входи та їх походження

| Вхід | Обов'язковий | Хто готує | Що містить |
|---|---|---|---|
| `case: CaseInput` | Так | Користувач через API R2 | indication, mechanism, scope, program_data, modality, development_stage, as_of_date |
| `pack: EvidencePack` | Так, може бути порожнім | R3 | sources, evidence з точними excerpt, retrieval_warnings, snapshot_id, synthetic |
| `ctx: RunContext` | Так | R2 | case_id, run_id, snapshot_id, as_of_date, mode, model, budget, trace |
| `market: RoleResult` | Ні | Вузол market; передає pipeline R2 | Ринок, можливості, claims, gaps |
| `ip_licensing` | Ні | IP-вузол; передає pipeline R2 | Права, ліцензійні обмеження та прогалини у форматі RoleResult або його JSON dict |
| `science: RoleResult` | Ні | R4; передає pipeline R2 | Наукова теза та її невизначеності |
| `clinical: RoleResult` | Ні | R4; передає pipeline R2 | Клінічний план, milestones і невизначеності |

Додаткові результати — контекст, а не незалежні докази. Їхні evidence_ids
повинні належати переданому pack. Відсутній результат записується у
context_availability та unknowns. Відсутність IP не означає відсутності бар'єрів.

## Процес

Виклик: `await analyze_partnerships(case, pack, ctx, market=market,
ip_licensing=ip_result, science=science, clinical=clinical)`.

1. `prepare_partnerships_inputs` викликає `assert_pack`, звіряє snapshot і дати,
   перевіряє ролі додаткових входів, їхні claims та посилання.
2. LLM отримує case, повні sources і evidence, effective as_of_date,
   snapshot_id, synthetic, retrieval_warnings, upstream_context та
   context_availability. Очікувана схема — `PartnershipsAnalysis`.
3. `ctx.model.generate_structured("partnerships", payload,
   PartnershipsAnalysis, ctx)` викликається один раз. Адаптер відповідає за
   завантаження prompt за ID. Сам вузол не виконує мережевих запитів.
4. `PartnershipsAnalysis.model_validate` перевіряє типи та обов'язкові поля.
5. `validate_partnerships_result` через `_walk` і `_validate_claims` перевіряє
   вкладені посилання, scope, basis, формати й пояснення прогалин.
6. `identify_partnerships_gaps` збирає вже записані невідомості, потреби в
   даних та неперевірені claims, прибирає точні повтори. Нового аналізу немає.
7. Функція збирає `RoleResult`: claims, risks, unknowns,
   change_conditions і section_content. Повна карта доступна в
   `result.section_content[0].structured_data["partnerships"]`.

## Класи й поля

| Клас | Призначення | Точні поля |
|---|---|---|
| `StrictOutput` | Базова сувора схема | Немає полів; config extra=forbid |
| `RoleResult` | Спільний кінцевий результат вузла | `role_id`, `summary`, `position`, `claims`, `risks`, `unknowns`, `change_conditions`, `section_content` |
| `PartnershipClaim` | Твердження з доказами | `id`, `text`, `provenance`, `support_status`, `evidence_ids`, `assumptions`, `scope`, `importance` |
| `Finding` | Картка факту/гіпотези/прогалини | `value`, `basis`, `claim_ids`, `assumptions`, `unknowns` |
| `PartnerFit` | Відповідність партнера | `work_direction`, `portfolio`, `capabilities`, `partner_needs`, `rationale` |
| `CollaborationOption` | Оцінка одного формату | `format`, `assessment`, `rationale`, `prerequisites`, `unknowns` |
| `DataGap` | Дані для предметної розмови | `missing_result_or_data`, `why_needed_for_discussion`, `evidence_needed` |
| `PartnershipTiming` | Етап та умови | `stage`, `milestone`, `readiness`, `conditions` |
| `PartnershipDependency` | Залежність та перевірка | `kind`, `finding`, `impact`, `next_check` |
| `PartnershipCheck` | Питання, доказ та вплив | `question`, `evidence_needed`, `decision_if_positive`, `decision_if_negative`, `claim_ids` |
| `InvestmentImplication` | Умовний вплив на сценарій | `finding`, `scenario_effect`, `conditions`, `next_check` |
| `PartnerCandidate` | Партнер або категорія | `id`, `kind`, `identity`, `fit`, `required_competencies_and_resources`, `collaboration_options`, `project_offer`, `discussion_gaps`, `timing`, `dependencies`, `risk_ids`, `next_checks`, `investment_implications`, `partner_interest`, `deal_readiness` |
| `PartnershipsAnalysis` | Вся відповідь моделі | `summary`, `position`, `claims`, `candidates`, `candidate_search_unknowns`, `risks`, `unknowns`, `next_checks`, `change_conditions`, `limitations` |

`Finding` — картка конкретного поля, а не окремий запис з ID:
- documented: value та локальні supported claims з evidence;
- hypothesis: value, assumptions та unverified/unknown claims;
- unknown: value=null та пояснені unknowns.

Зацікавленість партнера й готовність до угоди дозволені лише як documented
або unknown. Відповідність портфеля сама по собі не підтверджує їх.
Чотири формати завжди оцінюються окремо; insufficient_data не означає
непридатність. `timing.readiness=conditional` означає умови для розгляду
партнерства, а не обіцянку укласти угоду.

## Конкретний синтетичний приклад

R3 передає `e1`: «Fictional Partner A researches synthetic target X», source
`s1`, synthetic=true. Локальний claim `partnerships.partner_direction` має
support_status=supported та evidence_ids=["e1"].

`PartnerCandidate.fit.work_direction → Finding.claim_ids →
partnerships.partner_direction → evidence_ids=["e1"] → Evidence.source_id=s1`.

Цей уривок може обґрунтувати напрям роботи, але не інтерес до нашого проєкту:
`partner_interest={value:null, basis:"unknown", claim_ids:[], assumptions:[],
unknowns:["Немає підтвердження інтересу"]}`.

За відсутності IP-контексту dependency.kind="ip_licensing" містить unknown
finding: права на передачу треба перевірити. Для licensing prerequisite —
підтвердження власника та права ліцензування. За відсутності human relevance
discussion_gaps запитує перевірені дані R4. InvestmentImplication описує лише
умовний вплив на ресурси чи фінансування, без вигаданої суми економії.

У `docs/examples/partnerships-synthetic.json` збережено повні входи й результати
двох офлайн-запусків з mock-адаптером: категорія партнера з прогалинами та
порожній пакет доказів. Це синтетичні приклади, не відповіді справжньої LLM.

## Покриття вимог

| Вимога | Поля результату |
|---|---|
| Потенційні партнери або категорії | candidates: id, kind, identity; або candidate_search_unknowns |
| Напрям, портфель, можливості, потреби та відповідність | fit.work_direction, portfolio, capabilities, partner_needs, rationale |
| Спільне дослідження, розробка, ліцензія, придбання | collaboration_options: рівно чотири різні format, assessment, rationale, prerequisites, unknowns |
| Що пропонує проєкт | project_offer, required_competencies_and_resources |
| Чого бракує для розмови | discussion_gaps: missing_result_or_data, why_needed_for_discussion, evidence_needed |
| Коли доцільне партнерство | timing: stage, milestone, readiness, conditions |
| Ризики й залежності | risk_ids → risks; dependencies, обов'язково IP/licensing |
| Наступні перевірки та докази відповідності | next_checks: question, evidence_needed, decision_if_positive/negative, claim_ids |
| Наслідки для інвестиційних сценаріїв | investment_implications: finding, scenario_effect, conditions, next_check |

## Реалізовано та чекає інтеграції

Реалізовано: локальні типи, prompt, підготовка, один виклик спільного інтерфейсу
адаптера, структурні перевірки, gaps, результат і офлайн-тести.

Актуальний main `7ea5e96` містить `RoleId.PARTNERSHIPS` та
`RoleId.IP_LICENSING`. Вузол повертає спільний `RoleResult` з
`role_id="partnerships"`; IP-контекст також приймається як спільний
`RoleResult` або його JSON dict. Тимчасові класи результату та IP-контексту
прибрано. Тести перевіряють повторне читання результату спільним контрактом.
Контракти й frontend отримано з опублікованого main без власних правок.

Результат використовує існуючу секцію commercial_opportunity. R2 має
об'єднати її structured_data.partnerships з market, без перезаписування
market-внеску. Нової секції Report немає.

Чекає: реальний адаптер і реєстрація prompt R2, pipeline, Report builder,
frontend від R1, узгодження з фактичним IP-вузлом після merge, семантичний
аудит R3, перевірка науки/етапу R4 та реальна evaluation. Mock-тести не
доводять factual accuracy, юридичну істинність, захист від hallucinations
або prompt injection. Вузол не визначає остаточне інвестиційне рішення.
