Ріно, продовжи перевірку frozen workflow з цієї точки. Live-перевірку зупинено на прохання Уляни; локальний HTTP сервер також зупинено.

Branch: `codex/whole-workflow-testing`, draft PR #56. Case: `case-bba4adb11384`, snapshot: `snap-run-81c3bf4976ff`. Робочий checkout: `/Users/ulanatancuk/Documents/ChatGPT/Unobio/workflow-checkout`. База й артефакти: `artifacts/r2-whole-workflow-55/`. Оригінальна база `vic.sqlite3` не змінена; SHA256: `cb82a04d26e030624fd645f9071e84bc2d611ad2f9d2626788ee36790911bbc7`. HTTP спроби використовували окрему копію `http-frozen.sqlite3`, без retrieval.

**Код, тести та ці docs включено в continuation commit гілки `codex/whole-workflow-testing`. Для продовження також потрібні база й весь локальний каталог артефактів, включно з probe scripts та component/context caches. Git сам по собі ignored artifacts не переносить. `.env` із ключами не передавати — використати власну live-конфігурацію.**

Що пройшло:
- Investment, Investment Threshold і Failure Miner: збережені live результати повторно пройшли schema/domain validators.
- Semantic Audit: live batches завершувалися; findings і blockers зберігаються.
- Chair: окрема перевірка зі збереженими upstream live результатами та live Chair components пройшла фінальне складання й незалежну schema/domain validation. Рекомендація `Conditional`, 3 claims, 3 arguments, 5 conditions, 7 diligence questions, усі 9 domain inventories покрито. Market blocker `market.commercial_program_stage_e4339ce5ae9c` збережено. Детерміністичний audit додаткових Chair claims не знайшов blockers.
- Збережені IP/licensing і Partnerships також повторно пройшли чинні доменні валідатори.

Chair artifacts: `remaining-nodes/chair.json`, `chair-validation.json`, `chair-*-component.json`, context/wire caches. Деталі: `docs/chair-live-request-budget.md`. Старі некоректні core components зберігаються в `remaining-nodes/prior-chair-components/`; їх не використовувати замість актуальних.

Важливі локальні виправлення:
- Chair: компактна lossless audit table, відповідні audit reasons у review slices; grouped dispositions з explicit item IDs і розгортанням у чинний контракт; adaptive review slices; усунення повторного inventory copied upstream wrappers; окремий diligence link plan та narratives; focused questions без catch-all; окремі synopsis calls для oversized linked records.
- Раннє відхилення Chair conflicts із claims чужих/відсутніх ролей, unknown Reasons із claim IDs, change triggers без зміни recommendation. При об’єднанні review slices із різними bases фінальний unknown assessment очищує claim_ids; canonical provenance зберігається.
- Science/Translation: bounded fresh repair без replay великої invalid answer. Live Translation repair підтверджено на 11 153 bytes замість попередніх 23 187.
- Market: context-only supported/contradicted/mixed claims без evidence IDs отримують одне bounded correction на рівні batch.
- IP: listed patent потребує documented publication_number, known license — documented rights_granted; рання перевірка для correction.
- Pipeline: порожня Science/Translation wave під час downstream audit repair тепер повертає [], а не падає в asyncio.wait([]).
- Додано початкове lossless partitioning великого Market audit feedback із batch-specific identities. **Це виправлення ще не достатнє для останнього live input — див. блокер нижче.**

**Повний HTTP workflow до фінального звіту ще НЕ пройшов; live revision також не перевірений.** Окремо валідований Chair не означає успіх повного HTTP workflow.

Уляна погодила наступний режим: повторно використати валідовані live результати Science–Failure Miner, виконати Audit і Chair live, перевірити фінальний HTTP звіт. Harness `frozen_reuse_app.py` повторно використовує specialist result лише при першому виконанні ролі. Якщо live Audit вимагає repair, owners і dependents виконуються live, зі збереженням реальної pipeline repair logic. Audit і Chair не підміняються кешем. `frozen_app.py` — окремий harness для всіх вузлів fresh live. Обидва pin retrieval до того самого snapshot, логують фактичні request.content UTF-8 bytes, HTTP status, completion cap/effort, traces й outputs без API keys/headers.

**Поточний блокер:** останній run `run-0a7aff9f8530` завершився `market_request_budget` під час audit repair, до нових Market API calls. Помилка: `One exact Clinical context record exceeds the initial Market byte budget`. Audit запускає repair для Investment/Market. Весь Market feedback більше не передається одним великим масивом: findings partitioned у groups до 2 500 bytes, але деяка комбінація exact Clinical record + feedback group + schema/case/evidence все ще не вміщається в 13 500 bytes. Планер уже сформував інші запити на 13 500 та 12 910 bytes, потім відхилив indivisible context record.

Діагностика: `http-frozen/run-0a7aff9f8530-trace.json`, `*-wire-http.jsonl`, `*-active-trace.json`, `*-responses/`. Попередній `run-e25b92281bf4` відхиляв уже мінімальний запит із усім audit feedback. Fresh run `run-72f2851f0727` пройшов Science, Translation, Clinical, Market та зупинився на некоректному patent record IP; ця рання перевірка вже додана. `run-10db3f0d309d` виявив виправлену empty repair wave.

Наступний крок: зробити Market feedback partitioning адаптивним до фактичної повної serialized request size й найбільшого exact Clinical record. Зберегти всі findings/reasons/blockers і provenance, не обрізати Clinical context, не підвищувати initial 13 500 / repair 18 000 caps. Далі пройти audit repair, повторний audit, live Chair, audit додаткових Chair claims, report assembly/Report validation та GET фінального HTTP report. Якщо repair змінює upstream outputs, використовувати актуальні outputs, а не старі залежні caches.

Продовження з `services/api` (шляхи адаптувати):

    .venv/bin/python -m uvicorn frozen_reuse_app:app --app-dir ../../artifacts/r2-whole-workflow-55 --host 127.0.0.1 --port 8002 --log-level warning

В іншому терміналі:

    .venv/bin/python ../../artifacts/r2-whole-workflow-55/probe_frozen_http.py

Кожний запуск створює новий run; останній failed run не можна просто resume. HTTP база — clone, original retrieval не виконувати. Повторна окрема Chair перевірка: `probe_remaining.py --through chair --reuse-components`. Probe_remaining ловить exceptions і може завершитися exit 0 після FAIL — перевіряти фактичний PASS/artifact/domain validation.

Валідація: останній завершений full backend suite — 1 096 passing tests; після нього нові pipeline/feedback tests проходили окремо. Останній повтор усього suite не був дозволений, тому фінальний full suite після всіх останніх edits ще потрібно виконати. Ruff для останніх змінених файлів та git diff --check проходили. Для повного suite у цьому checkout потрібен тестовий `SEED_SYNTHETIC=true` (live .env має false); socket tests можуть потребувати network permission.

Snapshot синтетичний, бюджетних/часових operands немає. Numeric happy path, предметна інтерпретація та вплив low reasoning effort залишаються окремою перевіркою. Schema validation не встановлює клінічну чи комерційну істину. Інвентар і synopsis/group rationale також потребують domain review. Кількість context/component/batch calls може бути великою; останні traces не є повною статистикою всіх історичних спроб.
