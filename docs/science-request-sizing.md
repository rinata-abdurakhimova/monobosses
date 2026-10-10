# Science request sizing experiment

Deploy the API changes and start a new assessment. Refreshing an existing failed run does not rerun it.

`SCIENCE_REQUEST_TARGET_BYTES=10000` controls Science's UTF-8 wire request target, including instructions, compact response schema, JSON escaping and body envelope. This is a provisional application target, not a measured gateway token limit. 512 bytes are reserved for repair feedback.

The run trace records `science size breakdown`: original total, raw instructions, raw schema, combined instructions/schema/envelope, marginal form/metadata and marginal evidence bytes. Raw figures are descriptive and do not add up to the serialized total. All measurements are bytes, not tokens; successful provider calls also record token usage where supplied.

Science sends a compact request directly when it fits. Otherwise it reviews every character of formatted evidence in measured segments with exact character offsets. Gateway input rejection halves the review target down to 2000 bytes. The final result uses all reviews and carries a limitation: AI reviews can omit detail. Reviews are not new evidence; canonical sources stay unchanged. Other nodes are unchanged.

If even one character cannot fit or combined reviews exceed the synthesis target, Science fails explicitly without dropping sources. Final synthesis can still encounter a lower gateway limit; the trace retains its measured request size. Inspect original breakdown, segment sizes, synthesis size and gateway outcomes to tune the target. Tests verify Unicode/JSON-escape sizing and exact source-character coverage; they do not establish the live gateway limit.
