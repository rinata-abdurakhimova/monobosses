# Як працює ip_licensing

## Для чого він потрібен

Це вузол R5 для первинного огляду інтелектуальної власності й ліцензування.
Він пояснює відомі права, можливі обмеження та що ще потрібно перевірити.
Він не встановлює юридично, що продукт точно можна розробляти чи продавати.

**Реалізовано:** структуру, prompt 1.0.0, підготовку входів, один виклик через
інтерфейс адаптера R2, перевірку виходу, складання спільного RoleResult,
синтетичні приклади та офлайн-тести.

**Ще потрібно:** справжній адаптер R2, підключення до pipeline і Report,
патентні докази й змістовний аудит R3, перевірка патентного фахівця.
Нових API-запитів до Gemini або іншого провайдера під час реалізації не було.

## Звідки надходять дані

| Вхід | Хто готує / передає | Що саме містить | Обов’язковість |
| --- | --- | --- | --- |
| `case` | Користувач через API R2 | Захворювання, механізм, approach/program, за наявності modality, стадія, опис конкретної програми, дата аналізу | Обов’язковий |
| `pack` | R3; передає pipeline R2 | Sources із назвою, URL, датами, hash, synthetic; Evidence з ID, source_id, точним уривком, місцем у документі, scope та обмеженнями; snapshot_id і попередження | Обов’язковий; може бути порожнім |
| `ctx` | R2 | IDs кейсу/запуску, snapshot_id, дата, режим, model adapter, бюджет і trace | Обов’язковий |
| `science` | Науковий вузол R4 через pipeline | Молекула/мішень, механізм та наукові твердження, якщо доступні | Необов’язковий |
| `clinical` | Клінічний вузол R4 через pipeline | Застосування, популяція, план розвитку та відповідні твердження | Необов’язковий |
| `market` | Ринковий вузол R5 через pipeline | Конкуренти, комерційна географія та комерційний контекст | Необов’язковий |

Джерела для R3 можуть включати патентні реєстри та публікації заявок,
відомості про правовий статус/передачу прав, розкриття компаній і надані
ліцензійні договори. **Це потрібні види матеріалів, а не реалізовані тут
пошукові інтеграції.** Вузол отримує вже підготовлені уривки, не відкриває
реєстри й не шукає патенти сам.

`Source` — документ або запис. `Evidence` — конкретний уривок із нього.
`Claim` — твердження, яке модель побудувала з уривка.

Приклад: R3 передає документ `src-ip` та уривок `ev-ip`:
«Передача ліцензії потребує згоди». Модель створює
`ip_licensing.transfer_consent` із `evidence_ids=["ev-ip"]`.
Вузол перевіряє, що такий уривок існує. R3 перевіряє, що він справді
підтримує це твердження. Юрист перевіряє значення умови для конкретної угоди.

Висновок market не є патентним доказом. Якщо він назвав комерційний регіон,
це допомагає зрозуміти, де потрібна перевірка прав, але не доводить наявність
патенту в цьому регіоні. Твердження інших вузлів повинні посилатися на докази
з того самого переданого пакета. Самі вузли один одного не запускають.

## Виклик і рух даних

```python
result = await analyze_ip_licensing(
    case, pack, ctx,
    science=science_result,  # можна не передавати
    clinical=clinical_result,
    market=market_result,
)
```

1. `prepare_ip_licensing_inputs` перевіряє зв’язки evidence → source,
   дублікати, відповідність snapshot і дат кейсу/контексту, правильні ролі
   додаткових входів та їхні evidence IDs.
2. Готує payload: кейс, повні джерела й уривки, дати, synthetic,
   попередження, додаткові результати. Уривки не скорочуються.
3. `analyze_ip_licensing` викликає
   `ctx.model.generate_structured("ip_licensing", payload, IPLicensingAnalysis, ctx)`.
   Конкретної моделі, API-ключа чи клієнта провайдера в цьому вузлі немає.
4. Pydantic перевіряє структуру відповіді. `validate_ip_licensing_result`
   перевіряє посилання, scope, статуси відомостей і пояснення прогалин.
5. `identify_ip_licensing_gaps` збирає невідомості й потрібні наступні перевірки.
6. Вузол повертає `RoleResult`: claims, risks, unknowns, change_conditions
   і секцію з повною картою IP. Джерела й уривки залишаються у `pack`.

У разі timeout чи помилки адаптера виняток передається R2. Вузол не
повертає удаваний успішний результат і не робить власних повторних викликів.
R2 відповідає за timeout, retries, бюджет, trace і стан failed.

## Функції та методи — коротко

У самому `ip_licensing.py` це **функції**: вони оголошені поза класами. Вузол також використовує **методи** адаптера й Pydantic-моделей.

| Функція вузла | Що робить |
| --- | --- |
| `prepare_ip_licensing_inputs` | Перевіряє вхідні дані та готує payload: кейс, джерела, уривки, дати й додатковий контекст |
| `_walk` | Допоміжна функція: проходить усі вкладені об’єкти, списки й словники для перевірки полів і збирання прогалин |
| `validate_ip_licensing_result` | Перевіряє посилання, дублікати, scope, відокремлення документованих даних від припущень і пояснення прогалин |
| `identify_ip_licensing_gaps` | Збирає невідомості, умови, яких бракує, та наступні перевірки в один список без повторів |
| `analyze_ip_licensing` | Керує всім процесом: підготовка → один виклик моделі → перевірка → складання `RoleResult` |

| Використаний метод / зовнішня функція | Що робить |
| --- | --- |
| `ctx.model.generate_structured` | Метод адаптера R2: отримує prompt ID, payload і схему очікуваної відповіді; повертає структуровану відповідь моделі |
| `model_validate` | Метод Pydantic: створює або перевіряє об’єкт за правилами відповідного класу |
| `model_dump` | Метод Pydantic: перетворює об’єкт на словник; `mode="json"` також переводить дати й enum у формат для JSON |
| `date.isoformat` | Метод дати: записує дату у вигляді `YYYY-MM-DD` для payload |
| `assert_pack` | Спільна функція R2: перевіряє цілісність пакета доказів; при проблемах зупиняє виконання |

## Структура класів

| Клас | Коротке призначення | Поля |
| --- | --- | --- |
| `StrictOutput` | Базові правила перевірки структури й тексту | Полів даних немає; `model_config` — налаштування перевірки |
| `IPClaim` | Твердження з ID `ip_licensing.*`, джерелом походження, статусом підтримки й evidence IDs | `id`, `text`, `provenance`, `support_status`, `evidence_ids`, `assumptions`, `scope`, `importance` |
| `IPFinding` | Одне поле з документованим значенням, припущенням або невідомістю | `value`, `basis`, `claim_ids`, `assumptions`, `unknowns` |
| `PatentRecord` | Одна відома публікація патенту чи заявки | `id`, `record_type`, `publication_number`, `title`, `applicants`, `owners`, `legal_status`, `status_as_of`, `protected_subjects`, `territories_and_term`, `relevance`, `unknowns` |
| `ProtectedSubject` | Що може бути захищене: молекула, застосування, виробництво тощо | `category`, `description` |
| `TerritoryTerm` | Одна територія, доступний статус і підтверджена дата завершення захисту або прогалина | `territory`, `confirmed_expiry_date`, `status_as_of`, `protection_status`, `claim_ids`, `unknowns` |
| `LicenseRecord` | Одна відома ліцензія з окремими полями прав і обмежень | `id`, `patent_ids`, `licensors`, `licensees`, `rights_granted`, `exclusivity`, `territory`, `term`, `field_of_use`, `assignment_restrictions`, `sublicensing_restrictions`, `other_restrictions`, `unknowns` |
| `LicensableAsset` | Права, know-how, дані, процес або матеріал для потенційного ліцензування | `id`, `asset_type`, `patent_ids`, `license_ids`, `description`, `control_of_rights`, `licensing_uncertainties` |
| `LicensingOption` | Можливий формат угоди, активи, підстава, передумови та невідомі умови | `id`, `format`, `asset_ids`, `rationale`, `prerequisites`, `unknown_terms` |
| `PatentBarrier` | Можлива проблема, діяльність, якої вона стосується, наслідок і перевірка | `id`, `patent_ids`, `license_ids`, `concern`, `affected_activity`, `consequence`, `next_check` |
| `FTOAssessment` | Огляд можливих бар’єрів і незавершених перевірок свободи використання | `status`, `assessment`, `barriers`, `missing_checks` |
| `DealDataGap` | Яких даних бракує для угоди, що отримати й чому це важливо | `topic`, `missing_data`, `evidence_needed`, `impact_on_deal` |
| `LegalQuestion` | Конкретне питання фахівцю та вплив різних відповідей на рішення | `question`, `why_it_matters`, `evidence_needed`, `decision_if_positive`, `decision_if_negative`, `claim_ids`, `patent_ids`, `license_ids` |
| `IPImplication` | Можливі наслідки для партнерства та інвестиції | `finding`, `partnership_impact`, `investment_impact`, `next_check` |
| `CoverageFinding` | Чи є відомості в одному з дев’яти напрямів, чи даних недостатньо | `status`, `claim_ids`, `unknowns` |
| `IPLicensingAnalysis` | Повна структурована відповідь моделі, що об’єднує всі ці блоки | `summary`, `position`, `claims`, `patents`, `rights_and_licenses`, `licensable_assets`, `licensing_options`, `freedom_to_operate`, `deal_data_gaps`, `specialist_questions`, `implications`, `coverage`, `risks`, `unknowns`, `change_conditions`, `limitations` |

`IPClaim` успадковує поля спільного `Claim`; у таблиці перелічено всі його поля, включно з успадкованими. `IPLicensingAnalysis` об’єднує вкладені об’єкти: наприклад, `patents` — список `PatentRecord`, а `claims` — список `IPClaim`.

Спільні класи, які також використовує вузол:

| Клас | Коротке призначення | Поля |
| --- | --- | --- |
| `Risk` | Ризик і наступна перевірка | `id`, `description`, `priority`, `claim_ids`, `impact`, `next_check` |
| `SectionContent` | Одна секція результату | `key`, `summary`, `claim_ids`, `limitations`, `structured_data` |
| `RoleResult` | Повний результат вузла для pipeline | `role_id`, `summary`, `position`, `claims`, `risks`, `unknowns`, `change_conditions`, `section_content` |

`claim_ids` посилаються на твердження; `evidence_ids` — на уривки доказів. Полів `score` або `supports_id` у цих класах немає. Важливість твердження записана в `importance`, пріоритет ризику — у `priority`.

### Як відрізняються факт, припущення та невідомість

`IPFinding` має `value`, `basis`, `claim_ids`, `assumptions`, `unknowns`.

- `documented`: є значення та посилання на claims зі статусом supported.
  Це документована відомість за відповіддю моделі; змістову підтримку ще перевіряє R3.
- `hypothesis`: є значення, посилання на unverified/unknown claims і явні
  припущення. Наприклад: «можна розглянути невиключну ліцензію, якщо власник погодиться».
- `unknown`: `value=null`, є пояснення прогалини. Наприклад:
  «поточний власник не встановлений; потрібен ланцюг передачі прав».

Заявник не автоматично є нинішнім власником. Публікація заявки не дорівнює
виданому патенту. Заголовок чи abstract не доводить точний обсяг охоронюваних
патентних вимог. Дату завершення захисту Python не обчислює з року подання.
`status_as_of` показує дату відомого статусу; це не підтвердження його актуальності сьогодні.

## Де знайти кожен потрібний вихід

Повний блок:
`result.section_content[0].structured_data["ip_licensing"]`.

| Твоя вимога | Поля результату |
| --- | --- |
| Патенти, заявки, власники, статус | `patents`: record_type, publication_number, applicants, owners, legal_status, status_as_of |
| Що захищене | `patents[].protected_subjects`: category та description |
| Території та строки | `patents[].territories_and_term`: territory, protection_status, status_as_of, confirmed_expiry_date, unknowns |
| Права, ліцензії, обмеження передачі | `rights_and_licenses`: licensors, licensees, rights_granted, exclusivity, territory, term, field_of_use, assignment_restrictions, sublicensing_restrictions, other_restrictions |
| Патентні бар’єри й свобода використання | `freedom_to_operate`: assessment, barriers із affected_activity, consequence, next_check; missing_checks |
| Предмет потенційної ліцензії | `licensable_assets`: asset_type, description, control_of_rights, patent_ids, license_ids, licensing_uncertainties |
| Варіанти ліцензування | `licensing_options`: format, asset_ids, rationale, prerequisites, unknown_terms |
| Дані для оцінки угоди | `deal_data_gaps`: topic, missing_data, evidence_needed, impact_on_deal |
| Питання патентному фахівцю та юристу | `specialist_questions`: питання, підстава, потрібні докази, вплив обох відповідей, посилання |
| Наслідки для партнерства й інвестиції | `implications`: finding, partnership_impact, investment_impact, next_check; також RoleResult.risks |
| Джерела фактів, відокремлення припущень | RoleResult.claims: provenance, support_status, evidence_ids, assumptions; basis у кожному IPFinding; claim_evidence_links, evidence_source_links; sources/evidence у pack |

`coverage` обов’язково містить усі дев’ять напрямів. Порожній список патентів
потребує пояснення браку даних. Він не означає, що патентів немає.
`source_requests` і `RoleResult.unknowns` містять зібрані прогалини.

## Конкретний синтетичний приклад

У тестовому пакеті є заявка `SYN-001`, заявник A, відомий власник B,
статус pending у вигаданій території й відомість про ліцензію C з потребою
згоди на передачу. Дата завершення захисту не надана.

Вихід збереже заявника A окремо від власника B, заявку окремо від патенту,
`confirmed_expiry_date=null`, пояснить відсутність строку, покаже можливу
затримку угоди через згоду та поставить питання щодо відповідної умови.
Можливий формат нової ліцензії буде припущенням із передумовою перевірки прав.
Ціни угоди чи гарантованого доходу він не створює.

Якщо пакет порожній, списки патентів, відомих ліцензій, активів і варіантів
угоди порожні; position=insufficient_data; FTO=unresolved; залишаються
прогалини, запити на дані й питання фахівцю. Це пояснений результат браку даних.

## Що піде далі

`partnerships` використає права, обмеження й можливі формати співпраці.
`investment` використає їх для фінансових сценаріїв, якщо будуть окремо
перевірені числові inputs. `chair` використає risks, unknowns та питання.
Це майбутнє підключення pipeline, а не вже запущені тут вузли.

R2 має зберегти весь RoleResult і пов’язаний pack. Нова роль додається в
RoleId, але нова дванадцята секція Report не створюється: цей блок належить
`critical_unknowns`; загальні risks і questions також передаються збирачу.
При об’єднанні contributions не можна перезаписати інші critical_unknowns.

Перед merge додавання RoleId/PROMPT_IDS та спосіб відображення IP-блоку
потрібно узгодити з R2 і споживачами. Локальна реалізація не дорівнює
перевіреній інтеграції чи остаточному юридичному висновку.
