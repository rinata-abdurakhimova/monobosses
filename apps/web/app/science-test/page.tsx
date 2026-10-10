"use client";

import { useState } from "react";
import Link from "next/link";

export default function ScienceTestPage() {
  const [busy, setBusy] = useState(false);
  const [output, setOutput] = useState<unknown>(null);
  const [indication, setIndication] = useState("");
  const [mechanism, setMechanism] = useState("");
  async function run() {
    setBusy(true);
    setOutput(null);
    try {
      const response = await fetch("/api/backend/diagnostics/science", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ indication, mechanism, scope: "approach" }),
      });
      setOutput(await response.json());
    } catch {
      setOutput({
        error:
          "The test connection failed. Try again after checking API deployment.",
      });
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="page-container">
      <h1>Science test with real evidence</h1>
      <p>
        Enter your real indication and mechanism. This searches PubMed,
        ClinicalTrials.gov and Open Targets, then runs only Science. The
        returned evidence and warnings are shown with the diagnostics. No
        committee report is created.
      </p>
      <p>
        <label>
          Indication{" "}
          <input
            value={indication}
            onChange={(event) => setIndication(event.target.value)}
            disabled={busy}
          />
        </label>
        <br />
        <label>
          Mechanism{" "}
          <input
            value={mechanism}
            onChange={(event) => setMechanism(event.target.value)}
            disabled={busy}
          />
        </label>
      </p>
      <p>
        Retrieval uses up to 3 PubMed records and 4 trial records per query.
        Complete retrieved excerpts are retained; this is a limited search.
      </p>
      <button
        type="button"
        disabled={busy || !indication.trim() || !mechanism.trim()}
        onClick={run}
      >
        {busy
          ? "Testing Science (up to four minutes)…"
          : "Run Science with real evidence"}
      </button>
      <p>
        <Link href="/">Back to assessment</Link>
      </p>
      {output !== null && (
        <>
          <h2>Result and request diagnostics</h2>
          <pre style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>
            {JSON.stringify(output, null, 2)}
          </pre>
        </>
      )}
    </div>
  );
}
