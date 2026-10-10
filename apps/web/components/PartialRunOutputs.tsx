import { analysisStatus, visibleFindings } from "@/lib/analysis-status";
import type { RunOutputs } from "@/lib/api/types";
import { AnalysisDetails } from "@/components/AnalysisDetails";

const names: Record<string, string> = {
  science: "Science",
  translation: "Translation",
  clinical: "Clinical",
  market: "Market",
  ip_licensing: "IP / licensing",
  partnerships: "Partnerships",
  investment: "Investment",
  investment_threshold: "Investment Threshold",
  failure_miner: "Failure Miner",
  audit: "Semantic Audit",
  chair: "Chair",
};

export function PartialRunOutputs({ outputs }: { outputs: RunOutputs }) {
  const hasAttempts = outputs.nodes.some((node) => (node.attempt ?? 0) > 0);
  const order = Object.keys(names);
  const nodes = [...outputs.nodes].sort(
    (a, b) => order.indexOf(a.role_id) - order.indexOf(b.role_id),
  );
  return (
    <section
      className="panel partial-run-outputs"
      aria-labelledby="node-outputs-title"
    >
      <span className="eyebrow">SAVED NODE OUTPUTS</span>
      <h2 id="node-outputs-title">What the assessment has produced</h2>
      <p>
        These are individual node outputs. A final committee report is available
        only after the full workflow completes.
      </p>
      {!hasAttempts && (
        <p>
          {outputs.status === "failed"
            ? "No saved node outputs are available. This run may have stopped before analysis or started before output checkpoints were added."
            : "Analysis nodes have not started yet."}
        </p>
      )}
      <div className="role-grid">
        {nodes.map((node) => (
          <article
            className="role-card"
            key={node.role_id}
          >
            <h3>{names[node.role_id] ?? node.role_id}</h3>
            <span className="role-position">
              {(node.status ?? "not_started").replaceAll("_", " ")}
            </span>
            {node.error && (
              <p role="status">
                {node.error.message} ({node.error.code})
              </p>
            )}
            {node.stale && (
              <p>
                Earlier output — affected by a repair and not current for this
                run.
              </p>
            )}
            {node.result && (
              <>
                <p>
                  <strong>{analysisStatus(node.result).label}</strong>
                </p>
                {analysisStatus(node.result).explanation && (
                  <p>{analysisStatus(node.result).explanation}</p>
                )}
                <p>{node.result.summary}</p>
                <p>
                  {node.result.claims?.length ?? 0} claims ·{" "}
                  {node.result.risks?.length ?? 0} risks ·{" "}
                  {node.result.unknowns?.length ?? 0} evidence gaps
                </p>
                {(node.result.claims?.length ?? 0) > 0 && (
                  <div>
                    <h4>Findings from this analysis</h4>
                    <ul>
                      {visibleFindings(node.result.claims).map((claim) => (
                        <li key={claim.id}>
                          {claim.text} <small>({claim.support_status})</small>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                <details>
                  <summary>All claims, risks, gaps and analysis</summary>
                  <AnalysisDetails
                    value={{
                      claims: node.result.claims,
                      risks: node.result.risks,
                      unknowns: node.result.unknowns,
                      change_conditions: node.result.change_conditions,
                    }}
                  />
                  {node.result.section_content?.map((section, index) => (
                    <div key={`${section.key}-${index}`}>
                      <h4>{section.key.replaceAll("_", " ")}</h4>
                      <p>{section.summary}</p>
                      {(section.limitations?.length ?? 0) > 0 && (
                        <>
                          <h4>Limitations</h4>
                          <AnalysisDetails value={section.limitations} />
                        </>
                      )}
                      {section.structured_data != null && (
                        <AnalysisDetails value={section.structured_data} />
                      )}
                    </div>
                  ))}
                </details>
              </>
            )}
          </article>
        ))}
      </div>
    </section>
  );
}
