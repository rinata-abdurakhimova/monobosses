# R1 — Rinata: дизайн, Next.js, інтеграція та deploy

## Твій результат простими словами

Ти робиш сайт, на якому людина вводить питання, бачить аналіз і може перевірити кожен важливий висновок. Твоя робота закінчується, коли цей сценарій працює за спільним deployment URL, а не лише на твоєму ноутбуці.

Спочатку прочитай [порядок старту](README.md) та [контракт](../implementation-contract.md). Твої задачі: R1-01 → R1-02 → R1-03 → R1-04 у [реєстрі](../issues/README.md).

## Що ти пишеш

Код у `apps/web`: Next.js App Router + TypeScript. Орієнтовні файли:

- `app/page.tsx` — форма нового кейсу.
- `app/cases/[caseId]/page.tsx` — запуск, прогрес і поточний report.
- `components/CaseForm.tsx`, `RunProgress.tsx`, `RecommendationCard.tsx`, `ReportSections.tsx`, `RoleCard.tsx`.
- `components/EvidenceDrawer.tsx`, `EvidenceUpload.tsx`, `RevisionComparison.tsx`.
- `lib/api.ts` — типізовані функції createCase/startRun/getRun/getReport/addEvidence.
- `app/api/.../route.ts` — серверний proxy до Python API; не відкритий proxy до довільного URL.
- Конфігурація build/deploy та `docs/deployment.md`.

Не пишеш предметні prompts, retrieval чи розрахунки фінансів у React. UI показує отримані дані; не самостійно перераховує recommendation.

## Крок 1. Зроби сторінки на fixture — R1-01

1. Створи Next.js project у `apps/web`, запиши install/dev/build commands. Обери одну просту бібліотеку компонентів або базові власні компоненти; потрібна читабельність, а не окрема дизайн-система.
2. Намалюй структуру: input → progress → коротке рішення → 11 секцій → докази → додавання нового evidence. Почни з desktop, перевір вузький екран.
3. Форма: indication, mechanism — required; modality/stage/program data — optional. Поясни різницю approach/program; не вимагай назву препарату для оцінки підходу.
4. Підключи `contracts/fixtures/report-v1.json`. Поки fixture не готовий, використовуй локальний тимчасовий mock із явним написом «Синтетичний приклад» і заміни його після R2-01.
5. Покажи recommendation, rationale, scope, conditions, рольові summaries, 11 секцій, risks, unknowns і diligence questions. Порожня секція пояснює нестачу даних, не зникає.
6. Додай loading, empty, validation error, failed run та unavailable source states.

**Перевір:** порожня форма не запускає аналіз; довгий report читається; всі секції доступні; unknown не виглядає як підтверджений негативний факт. Передай screenshot і перелік компонентів R2/R5.

## Крок 2. Підключи Python API — R1-02

Потребує R2-01 і R2-02 для реальної інтеграції; дизайн роби раніше.

1. Отримай OpenAPI та working backend URL від R2. Створи TypeScript types, що відповідають schema; не копіюй кілька різних версій types по компонентах.
2. Реалізуй послідовність: POST case → POST run → polling GET run → GET report за `report_version`.
3. Polling зупиняється на completed/failed та при виході зі сторінки; не запускає новий analysis кожним tick. При timeout покажи status і можливість перевірити стан ще раз.
4. Розділи API access у `lib/api.ts`; fetch до Python проходить Next.js server proxy. Provider keys не потрапляють у browser bundle.
5. Відображай stage names зрозуміло: «Шукаємо докази», «Аналізуємо», «Перевіряємо висновки» тощо. Не показуй проміжний output як фінальне рішення.
6. Оброби error envelope і non-2xx responses. При retry створюється новий run лише після явної дії користувача.

**Перевір:** один click створює один run; failed API не лишає нескінченний spinner; після reload кейсу можна отримати збережений report. Передай R2 точний failed request, якщо контракт порушений.

## Крок 3. Докази та нова версія — R1-03

Потребує audit/claims від R3-03 і revisions від R2-03.

1. Recommendation має посилання на вирішальні claims; claim відкриває evidence; evidence показує excerpt, locator, title, дату, limitations і source URL, якщо він доступний.
2. Для inference/unknown поясни status. Невідомий source URL або private upload не перетворюй на вигаданий зовнішній link.
3. Додай text evidence та PDF upload за двома endpoints контракту. Покажи успішний import і його source ID; помилка parsing не запускає rerun.
4. Після import користувач запускає «Переглянути висновок» із parent report ID. Під час run залиш старий report доступним.
5. Порівняй before/after recommendations, зміни claims та пояснення. Якщо категорія не змінилась, так і покажи; UI не має удавати зміну.
6. Покажи номер версії, дату запуску та synthetic label для synthetic evidence.

**Перевір:** три кліки ведуть від рішення до конкретного уривка; v1 читається після створення v2; oversized/unsupported PDF дає зрозумілу помилку.

## Крок 4. Deployment — R1-04

1. Отримай від R2 working production command, healthcheck, env list, рішення щодо persistent storage та auth. Вибери з доступних команді hosting accounts; не створюй платні ресурси без погоджених умов.
2. Розгорни Python service і Next.js. Налаштуй `API_BASE_URL`, server-side API authentication, HTTPS та дозволені origins, якщо browser звертається напряму за погодженим контрактом.
3. Перевір, що restart API зберігає reports; якщо storage ephemeral, поверни це R2 як blocker.
4. Перевір upload limits і proxy timeouts. Background run не має тримати довгий HTTP request відкритим.
5. Пройди весь сценарій на deployment з synthetic кейсом та одним live input; перевір недоступне джерело й failed run.
6. Запиши URL, start/build commands, env names без values, кроки deployment, обмеження й перевірку в `docs/deployment.md`.

**Готово:** команда може відкрити URL, отримати report, відкрити evidence, додати доказ і побачити нову версію. Evaluation gates перевіряє вся команда у TEAM-01.

## Якщо щось блокує

- API не готове → продовжуй на fixtures; не вигадуй новий endpoint.
- У report немає поля → передай R2/R5 назву поля та приклад потрібного відображення.
- Немає пояснення evidence → це задача R3, а не привід приховати source.
- Бракує часу → прибирай декоративні елементи й необов’язкові панелі; залиш форму, 11 секцій, evidence, revision та errors.

