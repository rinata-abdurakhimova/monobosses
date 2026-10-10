# Chair live validation on the frozen R2 snapshot

Case `case-bba4adb11384`, snapshot `snap-run-81c3bf4976ff`.

Chair was assembled from saved live upstream results and live Chair components, with cached components revalidated. Independent schema/domain validation passed: Conditional recommendation, three Chair claims, three arguments, five conditions and seven diligence questions. All nine domain inventories were accounted for: Science 23, Translation 32, Clinical 58, Market 639, Investment 518, Partnerships 157, IP/licensing 222, Investment Threshold 1,260 and Failure Miner 3,870 items.

The canonical upstream context and audit were preserved, including the blocking Market claim `market.commercial_program_stage_e4339ce5ae9c`. A deterministic audit of the three additional Chair claims found no blockers. The original SQLite SHA256 remained `cb82a04d26e030624fd645f9071e84bc2d611ad2f9d2626788ee36790911bbc7`.

The wire protocol retains exact audit verdicts, evidence sets and blockers; relevant review slices also receive the corresponding audit reasons. Grouped dispositions explicitly enumerate every inventory item and expand into the existing individual contract. Review slices adapt to both audit and item bytes, and every generated request is measured against the configured cap with repair reserve. Copied upstream wrappers are excluded from the recursive inventory to avoid repeated accounting of the same inputs.

Live checks exposed invalid conflict role/claim relationships, unknown assessments carrying factual citations, unchanged change-trigger recommendations and a catch-all diligence question exceeding the request budget. These were corrected without relaxing the final Chair validator. Focused question plans distribute critical records across questions; oversized linked-decision explanations use individual synopsis calls rather than one large call. One isolated grouped-disposition request measured 9,499 bytes and expanded 24 explicit items. The latest successful change-trigger request measured 14,910 bytes. Historical attempts included failures and substantial cache reuse; the final continuation trace is not a complete count of all Chair calls.

Artifacts are ignored local files under `artifacts/r2-whole-workflow-55/remaining-nodes/`: `chair.json`, `chair-validation.json`, component files and continuation traces. They must be transferred separately from Git.

These checks establish contract and reference integrity on a synthetic snapshot lacking budget/time operands. They do not establish clinical or investment truth, quality of every synopsis/group rationale, or the effect of low reasoning effort. Numeric happy-path validation and domain review remain separate work. Chair validation alone does not establish a complete HTTP workflow or live revision.
