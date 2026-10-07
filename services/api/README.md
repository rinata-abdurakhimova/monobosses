# VIC API (services/api) — R2

Python-пакет `vic`: FastAPI, спільні Pydantic-контракти v1, mock-маршрути.
**Статус R2-01:** лише каркас + контракти + synthetic fixtures. Жодного реального аналізу, LLM чи SQLite.

## Встановлення та запуск
```bash
cd services/api
python -m venv .venv
source .venv/bin/activate          # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -e ".[dev]"
cp .env.example .env               # Windows: copy .env.example .env  (ключі НЕ комітимо)
python -m uvicorn vic.main:app --reload --port 8000
curl http://localhost:8000/health  # {"status":"ok"}
```
Swagger: http://localhost:8000/docs

## Команди
| Що | Команда (з `services/api`) |
|---|---|
| Згенерувати fixtures | `python scripts/generate_fixtures.py` |
| Перевірити fixtures | `python scripts/validate_fixtures.py` |
| Експорт OpenAPI | `python scripts/export_openapi.py` |
| Тести | `pytest -q` |
| Лінтер | `ruff check .` |

## Endpoints (контракт v1, розділ 3)
| Метод і маршрут | Тіло | Відповідь |
|---|---|---|
| `GET /health` | — | `{"status":"ok"}` |
| `POST /cases` | `CaseInput` | 201 `{"case_id"}` |
| `POST /cases/{case_id}/runs` | `{"mode","parent_report_id"}` | 202 `{"run_id"}` (**MOCK**) |
| `GET /runs/{run_id}` | — | `Run` |
| `GET /cases/{case_id}/reports/{version}` | — | `Report` |
| `POST /cases/{case_id}/evidence` | `{"title","text","published_at","synthetic"}` | 201 `{"source_id","evidence_ids"}` |
| `POST /cases/{case_id}/documents` | multipart `file`(PDF), `title`, `synthetic` | валідує тип/розмір, далі 501 |

Помилки завжди: `{"error":{"code","message","retryable"}}` — 422 `validation_error`, 404 `not_found`,
409 `incompatible_parent_report` / `mock_limitation`, 413 `payload_too_large`, 415 `unsupported_media_type`,
501 `not_implemented`, 503 `storage_unavailable`, 500 `internal_error`.

## MOCK-поведінка (R2-01) — що НЕ є реальним
| Місце | Що відбувається | Коли замінюється |
|---|---|---|
| `POST /cases/{id}/runs` (`api/mock_run.py`) | Копіює synthetic report у кейс; run одразу `completed` з warning `MOCK…`, header `X-VIC-Mock: true`, `model_version: "mock"` | R2-02 |
| Підтримка revision у mock | Лише v1 → v2 (потрібен `parent_report_id` = v1), інакше 409 `mock_limitation` | R2-02/03 |
| `storage.py` | In-memory, дані губляться після restart; засіяно `case-synthetic-01`, `run-synthetic-running`, `run-synthetic-failed` | R2-02 (SQLite) |
| `POST .../evidence` | Увесь текст = один excerpt; без chunking | R3 / R2-03 |
| `POST .../documents` | Перевірка типу/розміру, далі 501 | R2-03 (парсер R3) |
| `llm.py`, `pipeline.py`, `report_builder.py`, `evals/run.py` | Заглушки (`NotImplementedError`) | R2-02 / R2-03 |

Усі synthetic-дані мають `synthetic: true`; це **не** реальний аналіз.

## Імпорти для інших ролей
```python
from vic.contracts import (CaseInput, Source, Evidence, EvidencePack, Claim, RoleResult, SectionContent,
                           Risk, DiligenceQuestion, AuditFinding, AuditResult, CommitteeDecision,
                           Report, Revision, Run, UploadedDocument)
from vic.run_context import RunContext
```
Сигнатури функцій R3/R4/R5 — у контракті, розділ 4.

## Fixtures (`contracts/fixtures/`)
`case`, `evidence-pack`, `report-v1`, `report-v2`, `run-running`, `run-failed` (`.json`).
Єдине джерело — `src/vic/synthetic.py`; JSON генерується скриптом, руками не редагуємо.
Історія: v1 = Conditional (безпечну експозицію не встановлено), v2 = Do Not Invest (synthetic результат безпеки).

## Contract v1 changelog / рішення, потрібні від команди
| # | Питання | Default | Хто підтверджує |
|---|---|---|---|
| 1 | `Source.type` | peer_reviewed, preprint, registry, regulatory, company, patent, database, user_upload, synthetic | R3 |
| 2 | `AuditFinding.verdict` | значення `SupportStatus` | R3 |
| 3 | Форма `Disagreement` | topic, role_ids, summary, resolution | R5 |
| 4 | Додаткові ролі (critic/threshold/IP/partnerships) | `RoleId` = 7 prompt IDs контракту | R5 |
| 5 | «Достатньо program data» | ≥ 40 символів (`MIN_PROGRAM_DATA_CHARS`) | R4/R5 |
| 6 | Дзеркалення top-level у sections | `structured_data` для recommendation / key_risks / diligence_questions / sources | R1/R5 |
| 7 | Назва env для auth | `API_SHARED_SECRET` | R1 |
| 8 | Додаткові поля `Run` | `mode`, `parent_report_id` | R1 |
| 9 | `Source.published_at` | `date` (не datetime) | R3 |
| 10 | Claim: `source`/`supported`/`contradicted`/`mixed` вимагають `evidence_ids` | так | R3/R4/R5 |

## Відомі обмеження

R4/R5 використовують спільні моделі `vic.contracts`: `RoleResult.section_content` — список
секцій; market повертає `competitive_landscape` та `commercial_opportunity` окремо.
Clinical input серіалізується через Pydantic `model_dump`. Ризики ролей мають посилатися на
наявні claims і збігатися з відповідними записами `Report.risks`.
Повний `pytest -q` включає агентні тести зі справжніми контрактами; підміни `vic.contracts`
у тестах немає. Це перевірка сумісності, а не підтвердження якості інвестиційних рекомендацій.

In-memory сховище; немає auth, rate limits, реальних run-ів і PDF-парсингу; OpenAPI та fixtures треба
перегенерувати після змін моделей (`pytest` це перевіряє).
