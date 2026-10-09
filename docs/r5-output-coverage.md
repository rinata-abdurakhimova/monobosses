# Покриття R5: сім вузлів і 11 секцій

Стан 2026-10-09. Усі сім вузлів R5 реалізовані; main `a060c26` містить
підключення R2 до pipeline. На гілці `codex/r5-evaluation` додано checklist і cases.
Offline integration підтверджена; повний успішний live LLM-report та semantic
якість на цьому dataset ще не підтверджені.

Це карта реалізації за командним планом, не пряме підтвердження первинних вимог
організаторів або наявності незалежних реальних експертів. AI-ролі — перспективи
аналізу, не джерела незалежних доказів.

## Вузли R5

| Вузол | Що реалізує | Де повний результат у RoleResult |
| --- | --- | --- |
| market | Конкуренти, популяція, ціни, доступ і комерційна оцінка | section_content секцій competitive_landscape та commercial_opportunity |
| investment | План/капітал/час, funding gaps, три шляхи, future financing і стреси | section_content[0].structured_data["investment"] |
| failure_miner | Ланцюги й взаємодії ризиків, пріоритети та перевірки | section_content[0].structured_data["failure_miner"] |
| investment_threshold | Критерії now/next_stage, докази, прогалини й правила outcomes | section_content[0].structured_data["investment_threshold"] |
| partnerships | Partner fit, чотири формати, readiness, dependencies і gaps | section_content[0].structured_data["partnerships"] |
| ip_licensing | Права, патенти/ліцензії, території, бар'єри та legal questions | section_content[0].structured_data["ip_licensing"] |
| chair | Recommendation, аргументи, умови, conflicts і питання | ChairResult.role_result.section_content[0].structured_data["chair"] |

Claims, risks і unknowns зберігаються також у RoleResult; evidence/source — у pack
та Report. Chair канонічні ризики — decision.risks; порожній chair role_result.risks
є навмисним. Докладний chair role_result R2 зберігає серед report.roles.

## 11 секцій спільного Report

| Секція | Хто надає зміст |
| --- | --- |
| recommendation | Chair / CommitteeDecision |
| scientific_thesis | R4 science |
| human_translation_thesis | R4 translation |
| clinical_development_plan | R4 clinical |
| competitive_landscape | R5 market |
| commercial_opportunity | R5 market і partnerships |
| capital_to_milestone | R5 investment |
| key_risks | Рольові risks, failure_miner і Chair decision |
| critical_unknowns | Рольові unknowns, ip_licensing і Chair |
| diligence_questions | Питання ролей, investment_threshold і фінальні Chair questions |
| sources | R3 provenance та claim/evidence/source links усіх ролей |

R2 збирає Report, R1 відображає його. Семантичну підтримку перевіряє R3,
науку/clinical — R4. Не додаємо нову секцію для кожної додаткової ролі.

## Market target_population

Market повертає список `section_content`, а не старий вкладений `sections`.
Поточний шлях: `result.section_content[1].structured_data["target_population"]`
(commercial_opportunity; також можна знайти секцію за key).

| Поле | Значення |
| --- | --- |
| indication | Захворювання цільової популяції; null якщо невідомо |
| description | Пацієнти, яким потенційно призначене лікування; null якщо невідомо |
| eligibility | Критерії придатності; [] якщо немає даних |
| geography | Регіон; null якщо невідомо |
| access_limitations | Підтверджені бар'єри доступу або явно позначені припущення |
| claim_ids | Твердження з доказами/статусами, що підтримують опис |
| unknowns | Конкретні невідомості щодо популяції та доступу |

Кожне описане твердження про популяцію має бути в claims; Python перевіряє
існування посилань, R3 — відповідність доказу. Справжню клінічну eligibility
потрібно узгодити з R4. Пацієнти не є користувачами нашого застосунку:
застосунком користуються інвестори та фармкоманди.

Цей блок не генерує числові inputs автоматично й не прогнозує продажі.
За відсутності даних блок залишається присутнім з null/[] і поясненнями.
Повнота структури не дорівнює доведеній якості: live evaluation не проведено.

## Evaluation і межі підтвердження

[Rubric](../evals/rubric.md): 55 пунктів. [Dataset](../evals/cases/manifest.json):
21 synthetic case, expectations для всіх семи вузлів, 13 development / 8 holdout,
18 сімейств; before/after variants не перетинають splits.

За [офлайн-результатами](../evals/validation-results.json): 970 backend-тестів,
11 validator-тестів, 8 numeric probes (24 exact values і 3 expected rejections).
Це не оцінки реальних LLM-відповідей. Market numeric scenarios потребують
caller-reviewed inputs; pipeline зараз не передає `scenarios=` автоматично.

Очікування ще мають пройти [review R3/R4/R5](../evals/expectations-review.md).
[Error log](../evals/error-log.md) порожній; [evaluation report](evaluation-report.md)
містить структуру. Немає claims про expert agreement, unseen data або доведену
відсутність галюцинацій. IP screening не є остаточним legal/FTO clearance.

Деталі: [market](r5-01-handoff.md), [investment](r5-investment-handoff.md),
[Chair](r5-chair-handoff.md), [Failure Miner](r5-failure-miner-handoff.md),
[threshold](r5-investment-threshold-handoff.md), [partnerships](r5-partnerships-handoff.md),
[IP](r5-ip-licensing-handoff.md), [R2 integration](r2-full-workflow-handoff.md).
