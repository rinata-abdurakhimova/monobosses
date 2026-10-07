# monobosses

Віртуальний інвестиційний комітет для biotech underwriting. Стек реалізації: Next.js + Python. Наразі репозиторій містить продуктову концепцію та план реалізації; команди запуску будуть додані разом із кодом у R2-01/R1-01.

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

