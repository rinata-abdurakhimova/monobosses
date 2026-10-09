# Перевірочні кейси R5 — коротке пояснення

## Що вже готове

[Чекліст](rubric.md) — правила оцінювання. [Manifest](cases/manifest.json) — каталог
21 повністю синтетичний кейс: 13 development і 8 reserved holdout, 18 сімейств.
Кожен кейс має input, документи-докази та окремі expectations для всіх семи вузлів R5.
Це authored expectations: зміст ще має пройти review R3/R4/R5, не expert Unobio labels.

**Input + pack бачить модель. Expectations бачать перевіряльники.**
Не потрібен дослівний збіг текстів: перевіряємо факти, ризики, невідомості,
допустимі рішення та конкретні зміни після нових доказів.

## Де які файли

- `cases/manifest.development.json` — приклади для вдосконалення.
- `cases/manifest.holdout.json` — окремі сімейства для фінальної перевірки;
  не використовувати їхні результати для налаштування prompts.
- `cases/<id>/input.json` — чинний CaseInput.
- `cases/<id>/pack.json` — R3 JSON documents: повний короткий текст, дата,
  synthetic flag, scope, перевірювані уривки й обмеження.
- `cases/<id>/expectations.json` — потрібні факти з evidence/source IDs,
  важливі ризики, unknowns, заборонені твердження, допустима рекомендація
  з причиною, вимоги кожного вузла, rubric IDs і правила before/after.
- `numeric/` — 8 додаткових прямих перевірок наявного Python-коду розрахунків.
- `validate_cases.py` — офлайн-перевірка dataset та прямих розрахунків.
- `test_cases.py` — перевірки самого валідатора проти зіпсованих даних/витоків.
- `cases/dataset-lock.json` — hashes dataset і коду, з яким його звірено;
  це стартова фіксація контенту, не заморожена конфігурація live holdout run.
- `review-template.json` — форма ручної оцінки після отримання реальної відповіді.
- `validation-results.json` — фактичні офлайн-результати підготовки dataset;
  це не результати аналізу реальної LLM.

## Які ситуації перевіряємо

| Кейс | Основна перевірка |
| --- | --- |
| dev-01-sparse | Мало даних: чесні невідомості замість вигадок |
| dev-02-market-coverage | Шість категорій конкурентів, популяція, ціни й доступ |
| dev-03-budget-unknown | Невідомий бюджет і час не стають нулем |
| dev-04-partial-budget | Часткова сума не стає повним бюджетом; diligence окремо |
| dev-05-schedule-stress | Паралельні роботи, funding gap, додатковий стрес без подвійного рахунку |
| dev-06-role-conflict | Клінічні обмеження проти рекламної широкої популяції |
| dev-07-patent-barrier | Патент, територія, власник і невідомі права |
| dev-08-partner-fit | Відповідний партнер не означає готову угоду/фінансування |
| dev-09-cross-domain | Наукова прогалина впливає на clinical, капітал і партнерства |
| dev-10-safety-before | До вирішального доказу: safety-умова залишається відкритою |
| dev-11-admin-after | Новий адміністративний документ: рішення лишається Conditional |
| dev-12-safety-after | Вирішальна непереборна токсичність: Do Not Invest для цього кандидата |
| dev-13-ready-research | Готовність до обмеженого дослідницького етапу без обіцянки комерційного успіху |
| hold-01-animal-human | Результат на мишах не доводить користі людям |
| hold-02-currency-price | EUR/USD і ціна за курс/рік не змішуються |
| hold-03-license-restriction | Research-only ліцензія не дозволяє продаж/субліцензування |
| hold-04-injection | Інструкції всередині документу не керують відповіддю |
| hold-05-endpoint-gap | Біомаркер без валідації не дорівнює клінічній користі |
| hold-06-discontinued-unknown | Невідома причина припинення; майбутній outcome виключено за датою |
| hold-07-threshold-before | Визначений критерій ще не є отриманим результатом |
| hold-08-threshold-after | Позитивний доказ закриває конкретну прогалину, але не всі умови інвестиції |

Ці cases перевіряють усі сім вузлів і кінцевий Report через спільний pipeline.
Focus roles позначають головну перевірку case, але expectations задані для всіх семи.
Наукові facts і контекст R4 — inputs для business review; їхню достатність оцінює R4.

Набір містить позитивні спостереження, точні розрахунки та окремий кейс готовності
до обмеженого дослідницького етапу. Для нього Invest допустимий лише якщо реальні
outputs і audit підтверджують повноту даних та відсутність blockers; Conditional
допустимий за конкретної незакритої перевірки. Це не дозвіл фінансувати всі майбутні
клінічні стадії чи обіцянка комерційного успіху. Допустимі рішення мають змістовне
обґрунтування, а не лише збіг назви категорії.

21 кейс — готовий початковий набір для цього етапу, не вичерпний доказ якості всього
коду або всіх можливих клінічних/інвестиційних ситуацій.

## Як перевірено офлайн

З кореня репозиторію, без LLM/API і без читання `.env`:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=services/api/src /private/tmp/r5-ip-licensing-venv/bin/python evals/validate_cases.py --output /private/tmp/r5-validation.json
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=services/api/src /private/tmp/r5-ip-licensing-venv/bin/python -m pytest evals/test_cases.py -q -p no:cacheprovider
```

Валідатор використовує чинні CaseInput, R3 importer, evidence integrity,
Market input preparation, manifest validation runner R2 та справжню
`Pipeline._retrieve` із локальною тимчасовою SQLite. Він перевіряє імпорт,
відсікання майбутніх джерел і накопичення paired evidence; зупиняється до аналізу.
Виклики моделі й мережевого retrieval заборонені в цьому валідаторі.

Порожній пакет перевіряється на рівні існуючих node-тестів; pipeline evidence-only
вимагає хоча б один evidence item. Тому sparse-case містить мінімальний документ
про відсутність результатів, а не несумісний із runner порожній pack.

## Як отримати справжні evaluation результати пізніше

Після дозволу на live LLM/API, з налаштованим provider та доступним бюджетом,
R2 runner запускається з development manifest:

```bash
PYTHONPATH=services/api/src python evals/run.py evals/cases/manifest.development.json --output artifacts/r5-development
```

**Цю команду зараз не запускали.** Вона робить реальні model calls.
Відомий gateway context-limit для Market може блокувати запуск; маленькі packs
не гарантують, що prompt + schema + clinical/upstream context вмістяться.
Валідатор не називає символи токенами й не встановлює ліміти провайдера.

Runner читає тільки `input` і `pack` у model flow; expectations та leakage metadata
лишаються evaluator-only. Файли manifest із allowed_recommendations не треба
передавати моделі як завдання. Runner експортує run/report/snapshot/trace/summary,
але не оцінює semantic agreement з нашими expectations автоматично.

Для кожного output R3 звіряє claims з уривками, R4 — науку/clinical, R5 — бізнес,
фінанси й рішення, R2 — runtime. Заповнюємо review-template; критичні defects
зберігаємо окремо від score. Failed runs входять у denominator; run_failed
не дорівнює semantic FAIL, але також не accepted. LLM judge може допомогти,
однак його тут не реалізовано й його оцінка не замінює людський review.

Holdout запускаємо окремо тільки після review expectations і замороження
моделі/config/prompts; він не є прихованим від авторів. Якщо його використали для
tuning, потрібен новий незалежний набір. Результатів live holdout зараз немає.

## Важливі нюанси розрахунків і оновлень

Market у поточному pipeline не отримує caller `scenarios=`. Навіть коли pack містить
популяцію/ціновий аналог, у model response не очікуємо самостійно обчисленої
opportunity. Для перевірки формул використовуємо окремі прямі numeric probes із
reviewed inputs. Для реальних даних IDs самі не доводять придатність цих operands.
Zero-access probe — явно заданий контрольний counterfactual, а не факт із baseline.
Investment готує числовий план своїм поточним двоетапним способом; його model output
потім звіряємо з expectations та контрольними числами, без дослівного порівняння JSON.

Runner зберігає всі uploads у справі. Тому paired cases утворюють послідовності,
не паралельні гілки від одного parent: dev-10 → dev-11 → dev-12 та hold-07 → hold-08.
У revision pack повторюємо незмінні parent documents і додаємо лише новий документ;
R3 importer стабільно відтворює source/evidence IDs за вмістом.

Синтетичні джерела не мають реальних персональних/приватних даних або справжніх URL.
Leakage позначено partial: не виконували blind guessing й не доводили model cutoff.
Жодних runtime/cost, expert agreement або відсутності галюцинацій не вигадано.
