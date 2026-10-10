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

Existing output-token caps, request timeouts, retries, run cost/time settings, Market
and Science budgets, and retrieval sampling settings are unchanged. These are
separate from the Clinical budgets removed here. Restart the API and use a new run
for a live provider input-limit test; existing saved traces remain unchanged.
