# R4 — Arina: science, translation та clinical agents

## Твій результат простими словами

Ти пишеш три аналітичні функції: чому механізм може працювати, чи реально він допоможе людині та як це перевірити клінічно. Їхні висновки мають спиратись на evidence pack, а невідомі факти — залишатися невідомими.

Прочитай [старт](README.md) і [контракт](../implementation-contract.md). Порядок: R4-01 → R4-02 → R4-03. Не потрібно самостійно підключати PubMed чи робити API server.

## Що ти пишеш

Python у `services/api/src/vic/agents/science/`: `scientific.py`, `translation.py`, `clinical.py`, `prompts/`, предметні test cases. Функції `analyze_science`, `analyze_translation`, `analyze_clinical` повертають RoleResult зі спільних contracts R2 та використовують її LLM adapter.

## Крок 1. Scientific і human translation — R4-01

1. Візьми synthetic CaseInput/EvidencePack від R2/R3. До їх готовності склади checklist evidence й draft prompts у Markdown; після R2-01 використовуй спільні models.
2. Scientific prompt: human genetics, target expression, tissue, pathways, perturbation, animal evidence, prior programs; supporting і contradictory evidence. Явно відділи association від причинності.
3. Translation prompt перевіряє п’ять ланок: molecular effect → human exposure → target engagement → biological response → patient benefit. Для кожної покажи evidence, gap і limitation.
4. Обидві функції повертають конкретні claims зі stable keys, evidence IDs, support status, risks, unknowns та change conditions. Не повертай лише загальний paragraph.
5. Models calls тільки через adapter R2. Документи вставляй як дані; наявні в них instructions не змінюють agent task.
6. Перевір scope: результат конкретного кандидата не стає властивістю всіх препаратів механізму. Mouse efficacy не стає patient benefit.
7. Якщо claim не підтверджений, маркуй inference/unknown і сформулюй потрібне evidence. Не додавай красиву цитату з пам’яті моделі.

**Перевір:** synthetic pack без human safety дає missing safe exposure; негативний source не губиться; output проходить Pydantic validation. Передай R2 functions, R3 — claims для audit.

## Крок 2. Clinical development plan — R4-02

1. `analyze_clinical` отримує CaseInput, pack та science/translation outputs від pipeline. Не запускай ці agents сама повторно.
2. Опиши target population, clinically meaningful outcome, endpoint, comparator, biomarker strategy, sequence of studies і релевантні historical analogues.
3. Trial size — приблизна оцінка лише з assumptions або джерелом; якщо основи немає, сформулюй потребу в statistical design. Не генеруй точне число для заповнення поля.
4. Назви наступний milestone і докази, потрібні для його досягнення; передай R5, щоб financial module знав, що фінансувати.
5. Regulatory precedent познач як контекст, не guarantee approval. Unmet need/standard of care передай R5 як спільні клінічні inputs.
6. Сформуй risks, unknowns і diligence questions для synthesis. Наприклад, наявність biomarker не гарантує prediction of benefit.
7. Перевір два різні cases; однаковий code path, відмінні evidence/clinical assumptions. Не прописуй результат за назвою активу.

**Перевір:** план узгоджений з indication/modality/stage; safety gap не зникає; R5 може пояснити milestone за твоїм output.

## Крок 3. Перегляд після нового доказу та предметні expectations — R4-03

1. Для synthetic before/after запиши очікувану зміну claims до запуску системи: що спочатку unknown, що стало негативним evidence і чому.
2. R2 робить rerun з new snapshot. Твої функції працюють на новому pack з тими самими stable claim keys; історію збереження не реалізуєш самостійно.
3. Перевір, чи safety result стосується потрібного candidate/exposure/population. Якщо нерелевантний — аргументовано не змінюй тезу.
4. Додай три paired checks: вирішальний negative, релевантний positive, нерелевантний документ. Позитивний доказ не усуває всі інші risks автоматично.
5. Для dataset R5 запиши expected critical facts/risks, допустимі clinical interpretations і limitations. Познач team-reviewed; не називай себе або labels зовнішньою експертною оцінкою.
6. Розбери science/clinical errors з evaluation. Виправ prompts на development cases; holdout після використання для tuning більше не є незалежним.

**Готово:** новий вирішальний evidence змінює відповідний предметний claim; нерелевантний не породжує штучну зміну; evaluation має перевірні очікування, а не тільки «відповідь виглядає переконливо».

## Що передаєш

- R2: три async functions, prompt IDs/versions, examples і errors.
- R3: claims та запити на конкретні missing sources.
- R5: clinical plan, next milestone, meaningful benefit, risk/unknown/question lists та evaluation expectations.
- R1 отримує твої результати через спільний Report, а не окремий science endpoint.

## Твої GitHub Issues

- [R4-01: #5](https://github.com/rinata-abdurakhimova/monobosses/issues/5) — Написати scientific і human translation agents.
- [R4-02: #10](https://github.com/rinata-abdurakhimova/monobosses/issues/10) — Реалізувати clinical plan та визначення наступного milestone.
- [R4-03: #16](https://github.com/rinata-abdurakhimova/monobosses/issues/16) — Перевірити зміну science/clinical висновків і підготувати expectations.
