# Isolated live Science test

After deploying both API and website, open `/science-test` or use the link beside the assessment form. Click **Run live Science test**. No form entry is required.

This authenticated endpoint (`POST /diagnostics/science`) runs the real Science function with the configured model and one small fictional mouse evidence item. It calls no retrieval function, Translation, or later node. It creates no case or committee report. The result includes Science output, size-breakdown events and provider usage/error records, also on failure. Fictional evidence remains explicitly labelled synthetic.

The test takes at most 120 seconds; the website proxy allows 130 seconds. One diagnostic is allowed concurrently per API process. Results are shown on the page and are not persisted across refresh/restart. A success demonstrates this small Science request works; it does not establish that larger real assessments will work or reveal the exact gateway limit. Save the displayed diagnostics when investigating.
