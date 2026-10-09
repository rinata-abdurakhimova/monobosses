# R5 — Uliana: ринок, фінанси, голова комітету та evaluation

## Твій результат простими словами

Ти відповідаєш за запитання «Чи є сенс фінансувати цей підхід і за яких умов?» та за перевірку, чи система обґрунтовує відповідь. Пишеш market/investment/chair functions і координуєш evaluation; технічний runner робить R2, дані та leakage checks — R3, science expectations — R4.

Прочитай [старт](README.md), [контракт](../implementation-contract.md) і розділ 7 [загального плану](../../team-work-instructions.md). Порядок: R5-01 → R5-02 → R5-03 → R5-04. Рубрику можна почати паралельно з R5-01, не чекати готового продукту.

## Що ти пишеш

Python у `services/api/src/vic/agents/business/`: `market.py`, `investment.py`, `chair.py`, `failure_miner.py`, `investment_threshold.py`, `partnerships.py`, `ip_licensing.py`, `calculations.py`, `prompts/`. Evaluation content: `evals/rubric.md`, case manifests, `evals/error-log.md`, `docs/evaluation-report.md`. Functions використовують models і LLM adapter R2.

## Крок 1. Competitive та commercial analysis — R5-01

1. На synthetic EvidencePack від R3 реалізуй `analyze_market`; до contracts v1 підготуй поля й prompts.
2. Відокрем current standard of care, approved therapies, clinical-stage competitors, same-target programs, alternative mechanisms і discontinued programs.
3. Поясни, яка перевага потрібна новому підходу: користь, safety, доступність, administration або інша evidence-backed differentiation.
4. Market opportunity оцінюй за доступною популяцією, treatment eligibility, географією, pricing analogues та assumptions. Disease prevalence не прирівнюй до доступного ринку.
5. Кожен major claim прив’яжи до evidence IDs. Відсутні pricing/access дані познач unknown і запит на джерело до R3.
6. Числові scenarios рахуй Python-функціями на явних inputs; model пояснює inputs/limitations, а не виконує неперевірний mental calculation.

**Перевір:** без pricing evidence немає вигаданої ціни; конкурентний advantage сформульовано відносно comparator; approved та investigational не змішані.

## Крок 2. Investment scenario — R5-02

Потребує clinical plan/milestone R4-02 і market R5-01.

1. `analyze_investment` читає їх outputs через pipeline R2. Зрозумій, який результат програма має довести наступним.
2. Покажи capital і time до milestone, value inflection points, future financing і licensing/acquisition/development scenarios.
3. Якщо числових inputs недостатньо, поверни потрібні CRO/CMC/budget дані; не підставляй «типову» цифру без обґрунтування.
4. Для доступних inputs зроби downside/base/upside або діапазон із assumptions, currency, date, geography. Чітко відділи компанійні financials від бюджету активу.
5. У `calculations.py` покрий арифметику й одиниці meaningful tests: missing input, zero vs unknown, scale/currency consistency. Не обіцяй точний return без підстав.
6. Сформуй decision-changing фінансові gaps і next checks.

**Перевір:** можна відтворити розрахунок із перелічених inputs; витрати diligence не видаються за capital to develop program; мінімальні required financial outputs усі присутні або пояснено unknown.

## Крок 3. Голова, risks та фінальний зміст — R5-03

1. `synthesize_committee` отримує RoleResults і AuditResult; збирає вирішальні аргументи, а не підраховує votes.
2. Визнач scope й рекомендацію. Invest потребує достатньої підтримки тези; Conditional містить конкретні умови; Do Not Invest пояснює вирішальний бар’єр. Не використовуй фіксований score threshold без обґрунтування.
3. Покажи disagreements: хто що стверджує, які evidence релевантні, що лишилось unresolved. Згода agents не дорівнює незалежному доказу.
4. Об’єднай risks/unknowns без втрати критичних safety/translation issues. Для кожного risk: пріоритет, підстава, наслідок, next check.
5. Обери 5–10 diligence questions: чому важливе, які дані потрібні, як позитивна/негативна відповідь вплине на рішення. Не наповнюй список загальними питаннями для кількості.
6. Поверни CommitteeDecision; остаточний Report збирає R2. Нові claims голови передаємо R3 на final audit.
7. Для synthetic revision поясни зміну Conditional → Do Not Invest через конкретний новий safety evidence. У нерелевантному update не примушуй категорію змінитись.

**Перевір:** всі 11 секцій можуть бути зібрані; critical unsupported fact не керує рішенням; conditions перевірні; питання справді змінюють underwriting.

## Крок 4. Dataset, rubric та evaluation — R5-04

1. До налаштування на cases запиши рубрику: правильні critical facts, risks, допустимі рішення, evidence support, missing data behavior, financial validity, before/after behavior.
2. Почни з контрольних synthetic cases; розширюй до 12–20, якщо ресурси дозволяють. Кількість — внутрішня ціль, не доказ загальної точності.
3. Маніфест кожного case: ID, family, input, pack path, type, as-of date, expectations, allowed recommendations/rationale, leakage flags і split. Без особистих чи непублічних даних у public repo.
4. З R3 підготуй anonymized/temporal cases тільки за реального контролю. Obscure status не гарантує unseen; model release date не замінює documented cutoff. Якщо контроль не доведений, так і познач.
5. Development/holdout розділи за family, не за двома версіями одного case. Expected labels не надсилай у model context; identity mapping для anonymous cases теж окремо.
6. R2 реалізує runner; ти забезпечуєш manifest format, scoring і manual review. LLM judge допомагає знаходити defects, але не є єдиним суддею.
7. Порахуй per-case outcomes, denominators, critical omissions/unsupported claims, runtime/cost. Розбери failures у error log з owners; після fixes повтори affected development checks.
8. Заморозь config для holdout; запиши фактичні результати й обмеження в `docs/evaluation-report.md`. Не заявляй порівняння з Unobio experts, поки їхні оцінки не надані.

**Готово:** dataset і expectations відокремлені від runtime input; results відтворюються runner; критичні defects видимі незалежно від average score; report чесно описує team-reviewed proxy quality, а не доведену прибутковість.

## Погоджені сім вузлів R5

1. market — конкуренти, пацієнти, ціни, доступ і комерційна цінність.
2. investment — капітал/час до етапу, події зміни вартості, подальше фінансування й фінансові сценарії.
3. failure_miner — єдиний критичний опонент: проблема → вплив → наслідок → вплив на інвестицію → перевірка; взаємозв’язки ризиків.
4. chair — остаточна рекомендація за доказами, умови й фінальні питання.
5. investment_threshold — необхідний результат → докази → прогалина → вплив на рішення; поріг обґрунтованості вкладення не дорівнює окупності.
6. partnerships — відповідні партнери, формати співпраці та перевірки; відповідність не означає підтверджений інтерес.
7. ip_licensing — патентні факти, права, бар’єри й ліцензійні питання для фахової перевірки.

Усі сім входять у погоджений обсяг користувачки й реалізовані. У main `a060c26`
R2 підключила їх до спільного pipeline; offline integration перевірено.
Повний успішний live LLM-запуск і semantic evaluation ще не підтверджені.
Деталі ліцензування аналізує ip_licensing; partnerships розглядає партнерів;
investment використовує їхні висновки для фінансових сценаріїв. Evaluation
R5-04 — окремий перевірочний процес. Вузли можна готувати незалежно на явно
синтетичних fixtures; спільне підключення й запуск забезпечує R2.

## Поточний стан R5 — 2026-10-09

Реалізовані вузли, prompts, тести й handoff для всіх семи вузлів.
Чекліст: 55 пунктів. Dataset: 21 synthetic case з окремими expectations,
13 development / 8 reserved holdout за family; ці матеріали опубліковані
в `codex/r5-evaluation` (коміти `3643c8c` і `fc7dbbd`).

Офлайн-результати: 970 backend-тестів, 11 тестів dataset validator, 8 numeric probes.
Це перевірка коду/даних, не міркування реальної LLM. Expectations ще потребують
предметного review R3/R4/R5; після запусків потрібні per-case оцінки,
error log, frozen holdout run і фактичний evaluation report.

- [Пояснення й запуск офлайн-перевірок](../../evals/README.md).
- [Review tracker](../../evals/expectations-review.md).
- [Журнал помилок](../../evals/error-log.md) — порожній шаблон.
- [Evaluation report](../evaluation-report.md) — структура, без live-метрик.
- [Поточне покриття виходів](../r5-output-coverage.md).
- [Підключення й відомі runtime limitations](../r2-full-workflow-handoff.md).

Створення шаблонів і drafts не означає виконане людське review або закриті issues.

## Твої GitHub Issues

- [R5-01: #6](https://github.com/rinata-abdurakhimova/monobosses/issues/6) — Реалізувати competitive landscape та commercial analysis.
- [R5-02: #11](https://github.com/rinata-abdurakhimova/monobosses/issues/11) — Реалізувати capital/time to milestone та фінансові сценарії.
- [R5-03: #13](https://github.com/rinata-abdurakhimova/monobosses/issues/13) — Реалізувати голову комітету, risks та 5–10 diligence questions.
- [R5-04: #17](https://github.com/rinata-abdurakhimova/monobosses/issues/17) — Зібрати dataset, провести evaluation та оформити результати.
