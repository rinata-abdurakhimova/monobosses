# R3 — Victoria: дані, пошук та перевірка доказів

## Твій результат простими словами

Ти даєш агентам матеріали, на яких можна будувати висновки, і перевіряєш зв’язок між твердженням та доказом. Користувач має бачити не просто URL, а конкретний уривок, дату та обмеження.

Прочитай [старт](README.md) і [контракт](../implementation-contract.md). Порядок: R3-01 → R3-02 → R3-03. Предметні висновки узгоджуєш з R4/R5; не оцінюєш фінанси самостійно.

## Що ти пишеш

Python у `services/api/src/vic/evidence/`: `models` використовують R2 contracts; `importer.py`, `pdf_parser.py`, `normalization.py`, `retrieval.py`, `connectors/pubmed.py`, `clinical_trials.py`, `open_targets.py`, `audit.py`. Документація: `docs/source-registry.md`. Fixture: `contracts/fixtures/evidence-pack.json` у погодженні з R2.

## Крок 1. Спочатку локальний evidence pack — R3-01

1. Візьми models від R2-01. Якщо вони ще не готові, підготуй synthetic тексти й таблицю потрібних metadata; не створюй інший final schema.
2. Створи 3–5 коротких synthetic documents: підтримка механізму, обмежена translation, відсутня безпечна human exposure, комерційна невідомість та окремий негативний safety update. Всі позначені synthetic.
3. Для кожного source: ID, title, type, dates, hash; для evidence: source_id, точний excerpt, locator, scope, limitations. Не вставляй реальні DOI у synthetic material.
4. Напиши importer text/JSON та PDF parser із page locators. Якщо PDF scanned і текст не витягнуто, поверни `unreadable_document`; OCR можна відкласти, не повертай пустий «успішний» pack.
5. Deduplicate однакові documents за hash/identifier; не об’єднуй різні дослідження лише через однакову назву.
6. Поверни EvidencePack через спільні functions, передай R4/R5 та R2 для snapshots. User uploads маркуй user-provided, а не незалежно verified.

**Перевір:** excerpt буквально існує у source; locator правильний; повторний import не множить незалежні докази; недоступний текст не приховується.

## Крок 2. Підключи live retrieval поступово — R3-02

1. Створи source registry: назва, purpose, access method, credentials якщо потрібні (лише env names), rate limits, metadata й відомі gaps. API details перевіряй за офіційною документацією під час реалізації.
2. Почни з PubMed/PMC та ClinicalTrials.gov. Потім Open Targets, якщо він потрібен для disease/target identity. FDA/EMA і market sources додавай за реальними потребами R4/R5.
3. Normalize disease/target synonyms; якщо target неоднозначна, поверни candidates/уточнення, не обирай навмання.
4. Для case формуй запити на efficacy, safety, negative/terminated studies і релевантних competitor programs. Не обмежуйся пошуком позитивних abstracts.
5. Зберігай повний отриманий record/text snapshot та excerpt. Якщо доступний лише abstract, явно познач це; не придумуй full text.
6. Cache з retrieved_at/hash, bounded retries, provider-specific errors. `Нічого не знайдено` й `джерело не відповіло` — різні warnings.
7. За as-of date допускай тільки evidence із підтвердженою датою доступності; current trial record може містити later outcome, тому historical evaluation використовує frozen version, а не лише дату старту trial.
8. Перевір дві різні indication × mechanism. Статуси препаратів зі списку emerging drugs перевір перед live demo.

**Перевір:** дані приходять із live source, є metadata/уривки; одна невдала інтеграція не знищує інші; у evidence-only mode connectors не викликаються.

## Крок 3. Аудит claims і leakage checks — R3-03

1. Structural checks: source_id/evidence_ids існують, excerpt не порожній, locator доступний, provenance/scope відомі.
2. Semantic check: excerpt підтримує саме цей claim? Це люди чи тварини? Той самий candidate/популяція? Association чи causal evidence? Результат позитивний, негативний чи змішаний?
3. Повертай AuditFinding: supported/contradicted/mixed/unverified + конкретна причина + blocking для непідтвердженого критичного факту. LLM-assisted audit через adapter R2; на контрольних cases перевіряй вручну.
4. Якщо AI inference спирається на кілька premises, перевір їх окремо; не вимагай, щоб inference був прямою цитатою, але вимагай прозорого reasoning.
5. Перевір claims голови після synthesis. Простий валідний URL не означає успішний audit.
6. З R5 підготуй anonymization: вилучити прямі IDs і непрямі підказки, зберегти окрему evaluator mapping, провести blind identity guessing. Evidence-only packs не містять URLs/DOIs, які відразу розкривають identity; оригінальна provenance залишається поза model input.
7. Зафіксуй leakage limitations: неуспішне guessing не гарантує захисту, publication after release не доводить after cutoff, obscure drug не означає unseen.

**Готово:** audit ловить контрольний claim, який цитує mouse result як human efficacy; фінальний report не має критичних unsupported facts; evaluation manifest вказує фактичний спосіб контролю leakage.

## Передача та межі

- R2 отримує build/import/audit functions, snapshot content, warnings.
- R4/R5 отримують evidence pack і предметні limitations; запити на нові джерела повертають тобі.
- R1 отримує через API title/URL/excerpt/locator для drill-down.
- При браку даних поверни конкретний gap. Не заповнюй непублічні результати, IP чи ціни із здогадок.

## Твої GitHub Issues

- [R3-01: #4](https://github.com/rinata-abdurakhimova/monobosses/issues/4) — Реалізувати text/PDF import та synthetic evidence pack.
- [R3-02: #9](https://github.com/rinata-abdurakhimova/monobosses/issues/9) — Підключити live sources та пошук суперечливих доказів.
- [R3-03: #12](https://github.com/rinata-abdurakhimova/monobosses/issues/12) — Реалізувати аудит claim → evidence та leakage checks.
