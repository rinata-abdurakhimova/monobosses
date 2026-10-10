# Isolated live Science test

After deploying both API and website, open `/science-test` or use the link beside the assessment form. Enter your real indication and mechanism, then click **Run Science with real evidence**.

This authenticated endpoint (`POST /diagnostics/science`) accepts a CaseInput and runs actual external retrieval followed by Science. It calls no Translation or later node and creates no committee report. Results include the complete retrieved evidence pack, warnings, Science output and request diagnostics, including on model failure. Empty retrieval fails explicitly; synthetic evidence is never substituted.

The test allows 240 seconds including retrieval; the website proxy allows 250 seconds. One diagnostic runs concurrently per API process. Results are not persisted across refresh. Defaults reduce PubMed from 4 to 3 records per query and trials from 5 to 4; excerpts stay complete. Set RETRIEVAL_PUBMED_PER_QUERY=4 and RETRIEVAL_TRIALS_PER_QUERY=5 to restore the previous sample size. Actual byte reduction depends on record lengths and overlap; no fixed reduction or gateway success is guaranteed. Normal assessments use the same retrieval caps, but Translation still has separate request handling. Save displayed diagnostics when investigating.
