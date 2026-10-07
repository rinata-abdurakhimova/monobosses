# monobosses

Віртуальний інвестиційний комітет для biotech underwriting. Стек реалізації: Next.js + Python. Незалежна frontend-частина R1-01 реалізована у `apps/web` на явно позначеному синтетичному прикладі. Python API та live analysis ще не підключено.

## Запуск frontend preview

Потрібні Node.js 20.9+ та npm:

```sh
cd apps/web
npm ci
npm run dev
```

Відкрити `http://127.0.0.1:3000`. Перевірки: `npm run typecheck`, `npm run build`. [Frontend README](apps/web/README.md) описує стани, локальні дані та залежності від R2.

## Документація для команди

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

## Експертні перспективи й покриття R5

Поточний R5-01 market node реалізує перспективу **експерта з ринку та доступу
до лікування**: конкурентів, можливі переваги, цільову популяцію пацієнтів,
бар'єри доступу та комерційні сценарії. Це локальна реалізація без підключеного
live LLM adapter; семантичний аудит доказів надає R3. Prompt: **1.2.0**.
Локальна реалізація готова до передачі для інтеграції, але повна live-задача
R5-01 ще не підтверджена. Перевірка 2026-10-07: **47 тестів API пройшли,
із них 40 — market**. Окремі тимчасові спроби Gemini завершилися тайм-аутами
генерації; доступ до gemini-3.8-flash підтверджений, валідної відповіді немає.
API-ключі та тимчасовий адаптер не входять до реалізації R5.

[Карта всіх експертних ролей, 11 Required Output та фактичного покриття R5](docs/r5-output-coverage.md).
[Підключення market node для R2](docs/r5-01-handoff.md).


Офлайн-перевірка з кореня репозиторію:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest services/api/tests -q -p no:cacheprovider
```

Погоджений план R5: `market`, `investment`, `failure_miner`, `chair`,
`investment_threshold`, `partnerships`, `ip_licensing`. Реалізовано тільки
`market`; evaluation — окремий процес. R2 забезпечує adapter/runtime/Report,
R3 — evidence та аудит, R4 — клінічне узгодження, R1 — відображення.
