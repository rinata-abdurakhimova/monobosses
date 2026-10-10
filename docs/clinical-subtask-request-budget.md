# Clinical API input-limit testing

Clinical runs four sequential tasks: population, endpoints, safety, and planning.
Each sends its complete scoped records and validates the existing Clinical contracts.
Planning also receives the preceding subtask results. Critical claims, risks, gaps,
and limitations remain shared; selected evidence excerpts are preserved verbatim.

There is no Clinical application byte budget, repair reserve, segmentation, AI review,
or review-length cap. CLINICAL_REQUEST_TARGET_BYTES is retired and ignored if still
present in deployment variables. General node byte enforcement does not apply to
these four Clinical calls, including schema repairs. The gateway determines whether
the request fits; provider context-limit failures propagate without summarization or
smaller retries. Initial and actual request sizes remain recorded in the run trace.

Provider-limit diagnostics are enabled by default with PROVIDER_INPUT_LIMIT_TEST=true.
This also bypasses the older Science/Market/general-node input budgets, semantic
audit batching, run cost/time ceilings and LLM request timeouts. OpenAI-compatible
requests omit the completion cap. Set the flag false to use the older bounded
behavior elsewhere in the workflow; Clinical remains free of local byte budgets.
See deployment.md for transport and validation behavior that still applies.
Restart the API and use a new run for a live provider input-limit test.
