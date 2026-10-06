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
