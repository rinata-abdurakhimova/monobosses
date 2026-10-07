import { Icon } from "@/components/Icon";
import { PREVIEW_STEPS } from "@/lib/preview";

export function RunProgress({
  step,
  mode = "fixture",
}: {
  step: number;
  mode?: "fixture" | "mock-api" | "api";
}) {
  const steps =
    mode === "fixture"
      ? PREVIEW_STEPS
      : mode === "api"
        ? [
            "Validate input",
            "Retrieve evidence",
            "Analyze",
            "Audit claims",
            "Synthesize decision",
            "Save report",
          ]
        : [
            "Validate mock request",
            "Load fictional evidence",
            "Simulate analysis",
            "Simulate audit",
            "Simulate synthesis",
            "Complete the saved report",
          ];
  return (
    <section
      className="panel progress-panel"
      aria-labelledby="progress-title"
    >
      <span className="eyebrow">
        {mode === "api" ? "ASSESSMENT PROGRESS" : "SYNTHETIC WORKFLOW PREVIEW"}
      </span>
      <h1 id="progress-title">A considered conclusion takes a few steps.</h1>
      <p>
        {mode === "fixture"
          ? "No model or data source is being called. This animation previews how a future analysis will progress."
          : mode === "api"
            ? "Checking the saved Python run. You can reopen this URL to resume status checks without starting another assessment."
            : "The mock client polls one saved local run. No Python service, live research, or model call is running."}
      </p>
      <ol className="progress-steps">
        {steps.map((label, index) => (
          <li
            className={index < step ? "done" : index === step ? "current" : ""}
            key={label}
          >
            <span className="step-marker">
              {index < step ? (
                <Icon
                  name="check"
                  size={15}
                />
              ) : (
                index + 1
              )}
            </span>
            <span>{label}</span>
            {index === step && (
              <span
                className="spinner"
                aria-hidden="true"
              />
            )}
          </li>
        ))}
      </ol>
      <p
        className="sr-only"
        role="status"
        aria-live="polite"
      >
        {steps[Math.min(step, steps.length - 1)]}
      </p>
    </section>
  );
}
