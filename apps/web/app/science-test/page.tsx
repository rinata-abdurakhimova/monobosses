"use client";

import { useState } from "react";
import Link from "next/link";

export default function ScienceTestPage() {
  const [busy, setBusy] = useState(false);
  const [output, setOutput] = useState<unknown>(null);
  async function run() {
    setBusy(true);
    setOutput(null);
    try {
      const response = await fetch("/api/backend/diagnostics/science", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: "{}",
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
      <h1>Science connection test</h1>
      <p>
        This calls the configured model with fictional evidence. It runs only
        Science, without external source search, and does not create a committee
        report.
      </p>
      <p>
        <strong>Indication:</strong> Synthetic disease X<br />
        <strong>Mechanism:</strong> Inhibition of synthetic target Y
      </p>
      <p>
        Fictional test: target Y inhibition reduced a disease-X marker in one
        mouse experiment. No human data or independent replication is available.
      </p>
      <button
        type="button"
        disabled={busy}
        onClick={run}
      >
        {busy
          ? "Testing Science (up to two minutes)…"
          : "Run live Science test"}
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
