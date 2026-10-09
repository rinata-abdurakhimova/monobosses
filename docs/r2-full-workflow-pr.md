# Connect all committee nodes, PDF evidence and report details

The backend previously ran only five specialist nodes and could not call the merged Chair implementation. This change connects all nine specialists, Chair and semantic audit, preserves their complete outputs in the saved report, and displays all 11 perspectives in the frontend.

PDF uploads now parse and persist evidence without starting a run. Publication date and explicit program scope are supported; reruns include imported evidence in a new snapshot while retaining immutable report versions. The evidence-only evaluation runner exports reports, snapshots, traces and usage without sending evaluator labels to the model.

Validation: 970 backend tests and 40 frontend tests pass. TypeScript, OpenAPI contract drift, formatting, production build and git diff --check pass. HTTP integration exercises all real domain functions with deterministic model responses, revisions and SQLite reopening; browser checks confirm the integrated report and financial details.

Live acceptance remains incomplete: the mentor gateway accepts short requests but rejects Market with `Input exceeds the conservative input limit`. The same Market diagnostic also fails with gpt-5-mini. Compact schema/JSON encoding did not resolve the rejection. Follow-up #51, assigned to Uliana, reduces/splits the Market request within the existing gateway limits; this PR does not claim a successful full live run.

Related: #7, #14, #34, #8, #15. These issues remain open where live/deployment acceptance is still pending.

