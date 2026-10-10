"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import type { Run } from "@/lib/contracts/generated";
import { summarizeUsage } from "@/lib/usage";

type Trace = {
  available: boolean;
  trace_id?: string;
  usage: Array<{
    prompt_id: string;
    model?: string;
    attempt?: number;
    outcome?: string;
    input_tokens: number | null;
    output_tokens: number | null;
    latency_ms?: number;
    cost_usd?: number | null;
  }>;
  events: Array<{ stage: string; message: string }>;
  stage_durations_ms?: Record<string, number>;
  pricing: {
    llm_price_input_per_mtok?: number | null;
    llm_price_output_per_mtok?: number | null;
    llm_price_date?: string | null;
  };
};
const number = (value: number | null | undefined) =>
  value == null ? "Unavailable" : value.toLocaleString();
const money = (value: number | null | undefined) =>
  value == null ? "Unavailable" : `$${value.toFixed(6)}`;
const duration = (value: number | undefined) =>
  value == null ? "Unavailable" : `${(value / 1000).toFixed(1)} s`;

async function read<T>(path: string, signal: AbortSignal): Promise<T> {
  const response = await fetch(`/api/backend/${path}`, {
    cache: "no-store",
    signal,
  });
  const data = await response.json();
  if (!response.ok)
    throw new Error(data.error?.message ?? "Usage data could not be loaded.");
  return data as T;
}

export function UsageDashboard() {
  const [runs, setRuns] = useState<Run[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [trace, setTrace] = useState<Trace | null>(null);
  const [error, setError] = useState("");
  const [traceError, setTraceError] = useState("");
  const [loading, setLoading] = useState(true);
  const [refresh, setRefresh] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError("");
    read<Run[]>("runs", controller.signal)
      .then(setRuns)
      .catch((err: Error) => {
        if (!controller.signal.aborted) setError(err.message);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [refresh]);

  useEffect(() => {
    setTrace(null);
    setTraceError("");
    if (!selected) return;
    const controller = new AbortController();
    read<Trace>(`runs/${encodeURIComponent(selected)}/trace`, controller.signal)
      .then(setTrace)
      .catch((err: Error) => {
        if (!controller.signal.aborted) setTraceError(err.message);
      });
    return () => controller.abort();
  }, [selected, refresh]);

  const summary = summarizeUsage(runs);
  return (
    <div className="page-container usage-page">
      <div className="page-heading">
        <div>
          <span className="eyebrow">MODEL OPERATIONS</span>
          <h1>Usage &amp; traces</h1>
          <p>
            API usage and estimated model cost for the latest 200 saved runs.
          </p>
        </div>
        <button
          className="button button-secondary"
          disabled={loading}
          onClick={() => setRefresh(refresh + 1)}
        >
          Refresh
        </button>
      </div>
      {loading && <p role="status">Loading usage…</p>}
      {error && <p role="alert">{error}</p>}
      {!loading && !error && (
        <>
          <div className="usage-metrics">
            <section className="panel">
              <span className="eyebrow">AVERAGE / COMPLETED LIVE RUN</span>
              <h2>{money(summary.average)}</h2>
              <p>
                Cost known for {summary.priced} of {summary.completed} completed
                live runs.
              </p>
            </section>
            <section className="panel">
              <span className="eyebrow">ESTIMATED COST RANGE</span>
              <h2>
                {summary.min == null
                  ? "Unavailable"
                  : `${money(summary.min)} – ${money(summary.max)}`}
              </h2>
              <p>Only runs with recorded costs.</p>
            </section>
            <section className="panel">
              <span className="eyebrow">API CALL ATTEMPTS</span>
              <h2>{number(summary.calls)}</h2>
              <p>
                Across {runs.length} saved runs, including failures and retries.
              </p>
            </section>
          </div>
          <p>
            Estimates use each run’s recorded token rates. Cache discounts,
            gateway charges and charges for timed-out calls may differ from
            billing. Live runs can include development stubs; inspect run
            configuration before using this sample in a submission.
          </p>
          <section className="panel usage-table-wrap">
            <h2>Saved runs</h2>
            {!runs.length ? (
              <p>No saved runs yet. Start an assessment to collect usage.</p>
            ) : (
              <table className="usage-table">
                <caption>
                  Latest saved runs; unknown values remain unavailable.
                </caption>
                <thead>
                  <tr>
                    <th>Run / model</th>
                    <th>Status / mode</th>
                    <th>Calls</th>
                    <th>Input tokens</th>
                    <th>Output tokens</th>
                    <th>Estimated USD</th>
                    <th>Duration</th>
                    <th>Details</th>
                  </tr>
                </thead>
                <tbody>
                  {runs.map((run) => (
                    <tr key={run.id}>
                      <td>
                        <Link
                          href={`/cases/${encodeURIComponent(run.case_id)}?flow=api&run=${encodeURIComponent(run.id)}`}
                        >
                          {run.id}
                        </Link>
                        <br />
                        {run.model_version ?? "Unavailable"}
                      </td>
                      <td>
                        {run.status}
                        <br />
                        {run.mode ?? "Unspecified"}
                      </td>
                      <td>{number(run.usage?.calls)}</td>
                      <td>{number(run.usage?.input_tokens)}</td>
                      <td>{number(run.usage?.output_tokens)}</td>
                      <td>{money(run.cost_usd)}</td>
                      <td>{duration(run.latency_ms?.total)}</td>
                      <td>
                        <button
                          className="button button-secondary"
                          aria-pressed={selected === run.id}
                          onClick={() => setSelected(run.id)}
                        >
                          Trace
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>
        </>
      )}
      {selected && (
        <section
          className="panel usage-trace"
          aria-live="polite"
        >
          <h2>Trace: {selected}</h2>
          {traceError ? (
            <p role="alert">{traceError}</p>
          ) : !trace ? (
            <p>Loading trace…</p>
          ) : !trace.available ? (
            <p>
              No saved trace yet. Traces are persisted when a pipeline run
              finishes or fails. Refresh after completion; mock and fixture runs
              may have no trace.
            </p>
          ) : (
            <>
              <p>Trace ID: {trace.trace_id}</p>
              <p>
                Recorded pricing: input{" "}
                {money(trace.pricing.llm_price_input_per_mtok)} / 1M tokens ·
                output {money(trace.pricing.llm_price_output_per_mtok)} / 1M
                tokens · checked {trace.pricing.llm_price_date ?? "Unavailable"}
                .
              </p>
              <h3>Stage durations</h3>
              <ul>
                {Object.entries(trace.stage_durations_ms ?? {}).map(
                  ([stage, ms]) => (
                    <li key={stage}>
                      {stage}: {duration(ms)}
                    </li>
                  ),
                )}
              </ul>
              <div className="usage-table-wrap">
                <table className="usage-table">
                  <caption>Model call attempts</caption>
                  <thead>
                    <tr>
                      <th>Prompt / model</th>
                      <th>Attempt</th>
                      <th>Outcome</th>
                      <th>Input</th>
                      <th>Output</th>
                      <th>Duration</th>
                      <th>Estimated USD</th>
                    </tr>
                  </thead>
                  <tbody>
                    {trace.usage.map((call, index) => (
                      <tr key={index}>
                        <td>
                          {call.prompt_id}
                          <br />
                          {call.model}
                        </td>
                        <td>{call.attempt}</td>
                        <td>{call.outcome}</td>
                        <td>{number(call.input_tokens)}</td>
                        <td>{number(call.output_tokens)}</td>
                        <td>{duration(call.latency_ms)}</td>
                        <td>{money(call.cost_usd)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <h3>Events</h3>
              <ol>
                {trace.events.map((event, index) => (
                  <li key={index}>
                    <strong>{event.stage}</strong>: {event.message}
                  </li>
                ))}
              </ol>
              <details>
                <summary>Operational trace JSON</summary>
                <pre>{JSON.stringify(trace, null, 2)}</pre>
              </details>
            </>
          )}
        </section>
      )}
    </div>
  );
}
