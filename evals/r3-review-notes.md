# R3 review і виправлення — 2026-10-09

Джерело: коментар «R3 review від Rinata — evaluation cases (R4 pending)»,
наданий Uliana в чаті. Reviewer: Rinata / Codex. GitHub permalink не наданий.
Review стосувався dataset 1.0.0, cases commit fc7dbbd, snapshot e67b1f1.
Це evidence/provenance/leakage review R3, не R4-погодження і не LLM evaluation.

19 кейсів отримали R3 PASS; dev-06-role-conflict та hold-01-animal-human —
CHANGES_REQUESTED. Статуси перенесено в expectations-review.md без підвищення
загального label_status. Усі R4/R5 статуси залишаються NOT_REVIEWED.

## Правки dataset 1.0.1

- hold-01-animal-human: input mechanism змінено з target K на target H,
  відповідно до незміненого animal-result. Indication і approach scope збережено.
- dev-06-role-conflict: fact-02 тепер описує лише brochure. Вимога порівняння
  для Market/Chair містить premises fact-01 + fact-02 й обидва evidence IDs.
  Протокол не приписаний brochure. Validator відхиляє невідомі premises та
  неповні evidence links для таких порівнянь.
- Документи/excerpts не змінено, тому source/evidence IDs збережено.
- Manifest dataset_version і review-template expectations_version — 1.0.1;
  schema_version/rubric_version залишаються 1.0.0. Splits і рекомендації незмінні.
- Оновлено lock зі збереженням історії попередніх hashes. Явне UTF-8 читання
  в тестах прибирає залежність від системного кодування; LF-політику Git не змінено.

Обидва змінені кейси потребують короткого повторного R3 review. Правки не
означають нового R3 PASS автоматично. R4 все ще pending для всіх 21 кейсу.
Не закривати #52 і не заявляти завершене погодження або результати live evaluation.
Holdout поправлено за review вхідних матеріалів, без перегляду model outcomes.

## Офлайн-перевірки після правок

Усі 21 кейс пройшли schema/import/provenance/retrieval і lock checks.
8 numeric probes: 24 точні значення та 3 expected input rejections.
984 backend + 13 evaluation-тестів — разом 997 passed. Model calls: 0.
Commit і push не виконувалися.
