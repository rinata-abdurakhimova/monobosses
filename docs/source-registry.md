# Source registry (R3)

Реєстр зовнішніх джерел доказів. Деталі API перевірені за офіційною документацією на дату
реалізації; перед live-demo перевірити ще раз (ліміти й формати можуть змінитись).

## PubMed (NCBI E-utilities)

| Поле | Значення |
| --- | --- |
| Призначення | Peer-reviewed і preprint-публікації: ефективність, безпека, негативні результати |
| Доступ | `esearch.fcgi` (пошук ID) + `efetch.fcgi` (XML-записи), `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/` |
| Credentials | `NCBI_API_KEY` (необов'язково), `NCBI_EMAIL` (рекомендовано). Лише назви env-змінних |
| Ліміти | 3 запити/с без ключа, 10/с з ключем; перевищення → 429. Connector тримає інтервал 0.34 с / 0.11 с |
| Що отримуємо | Назва, abstract (по секціях), дата публікації, publication types, MeSH |
| Source type | `peer_reviewed`; `preprint`, якщо publication type = Preprint |
| Scope evidence | `approach` (abstract не приписується конкретній програмі автоматично) |
| Відомі gaps | Лише abstracts, **без full text**; відсутній abstract → запис пропускається з warning; дата може бути неточною (рік/місяць) → береться найпізніша можлива; abstract міг бути змінений після as_of |
| Historical (as_of) | Фільтр за Entrez date + датою публікації; для строгої оцінки потрібен frozen snapshot |

## ClinicalTrials.gov (API v2)

| Поле | Значення |
| --- | --- |
| Призначення | Реєстр клінічних досліджень: статуси, зупинені/відкликані, конкуренти |
| Доступ | `GET https://clinicaltrials.gov/api/v2/studies` (`query.cond`, `query.intr`, `filter.overallStatus`, `pageSize`) |
| Credentials | Не потрібні |
| Ліміти | ≈50 запитів/хв з однієї IP (**перевірити** в офіційній документації) |
| Відомі gaps | Поточний запис може містити пізніший результат → для historical-оцінки без frozen-версії не використовується |

## Open Targets Platform

| Поле | Значення |
| --- | --- |
| Призначення | Перевірка ідентичності target: чи назва з поля mechanism однозначна. **Evidence не створює** |
| Доступ | `POST https://api.platform.opentargets.org/api/v4/graphql`, query `search(entityNames:["target"])` |
| Credentials | Не потрібні |
| Логіка | З mechanism береться до 3 термінів, схожих на символ гена (JAK1, PD-1, TNF). Resolved — лише при точному збігу символу з одним target; інакше повертаються кандидати і warning, нічого не обирається автоматично |
| Відомі gaps | Синоніми (PD-1 → PDCD1) не розв'язуються автоматично; mechanism без символу гена не перевіряється (є warning) |

## Загальні правила

- «Нічого не знайдено» і «джерело не відповіло» — різні warnings; відмова джерела ≠ відсутність ризику.
- Один збій не зупиняє інші джерела.
- Retries обмежені (3 спроби, exponential backoff).
- У `evidence_only` режимі connectors не викликаються.