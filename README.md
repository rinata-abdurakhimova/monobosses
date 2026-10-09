# monobosses

Віртуальний інвестиційний комітет для biotech underwriting. Стек реалізації: Next.js + Python. Незалежна frontend-частина R1-01 реалізована у `apps/web` на явно позначеному синтетичному прикладі. Python API та всі експертні вузли підключено в спільний pipeline; офлайн-інтеграцію перевірено. Повний успішний live LLM-аналіз ще не підтверджено.

## Запуск frontend preview

Потрібні Node.js 22.18+ та npm (перевірено на Node 24):

```sh
cd apps/web
npm ci
npm run dev
```

Відкрити `http://127.0.0.1:3000`. Перевірки: `npm run typecheck`, `npm test`, `npm run build`. [Frontend README](apps/web/README.md) описує стани, локальні дані та залежності від R2. Для підготовки R1-02 у формі є окремий Mock API workflow; це локальна симуляція, а не підключення до Python. [Handoff R1-02](docs/r1-02-handoff.md) описує контракт, polling і наступні кроки інтеграції.

## Документація для команди

- [Railway deployment: website + Python API, configuration and remaining checks for #18](docs/deployment.md).

- [Продуктова концепція](virtual-investment-committee.md).
- [Загальні інструкції та розподіл ролей](team-work-instructions.md).
- [Почати роботу: хто що робить і в якому порядку](docs/roles/README.md).
- [Спільний технічний контракт v1](docs/implementation-contract.md).
- [18 задач із кроками, залежностями та критеріями готовності](docs/issues/README.md).

## Інструкції учасниць

| Виконавиця | Роль | Інструкція |
| --- | --- | --- |
| Rinata | R1: дизайн, frontend, інтеграція, deploy | [R1](docs/roles/r1-frontend.md) |
| Kateryna | R2: API та agent flow | [R2](docs/roles/r2-backend.md) |
| Victoria | R3: data/evidence та аудит | [R3](docs/roles/r3-evidence.md) |
| Arina | R4: science/translation/clinical | [R4](docs/roles/r4-science.md) |
| Uliana | R5: market/investment/chair/evaluation | [R5](docs/roles/r5-investment.md) |

Перший спільний крок — contracts та fixtures від R2. До їх готовності інші ролі можуть готувати UI, synthetic documents, prompts і evaluation rubric. Подальший порядок описано у реєстрі задач.

## Backend (services/api)

```bash
cd services/api
python -m venv .venv
.venv\Scripts\Activate.ps1          # macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"
copy .env.example .env              # macOS/Linux: cp .env.example .env
python -m uvicorn vic.main:app --reload --port 8000
```

Details, endpoints, mock behavior and contract changelog: [services/api/README.md](services/api/README.md).

## Експертні перспективи й покриття R5

Усі сім вузлів R5 реалізовані: `market`, `investment`, `failure_miner`,
`chair`, `investment_threshold`, `partnerships`, `ip_licensing`. R2 підключила
їх у main `a060c26`; R3 забезпечує evidence/audit, R4 — science/clinical,
R1 — відображення. Offline integration не доводить якість реальних LLM-відповідей.
[Підключення й live limitations](docs/r2-full-workflow-handoff.md).

Evaluation content доступний на `codex/r5-evaluation`: [rubric](evals/rubric.md),
21 [synthetic case](evals/cases/manifest.json) з окремими expectations,
13 development / 8 holdout, [guide](evals/README.md) та офлайн-валідатор.
За збереженими [результатами](evals/validation-results.json): 970 backend-тестів,
11 тестів валідатора, 8 numeric probes пройшли; live quality не оцінено.

Предметне узгодження expectations — [review tracker](evals/expectations-review.md).
[Error log](evals/error-log.md) порожній; [evaluation report](docs/evaluation-report.md)
підготовлений як структура. Предметне узгодження expectations виконують R3/R4 разом із R5.
[Карта всіх перспектив і 11 виходів](docs/r5-output-coverage.md).

Офлайн-перевірка з кореня репозиторію:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest services/api/tests -q -p no:cacheprovider
```

Evaluation R5-04 — окремий процес: підготовлені кейси й офлайн-тести
не замінюють фактичні model outputs, предметний review і підсумкові метрики.
