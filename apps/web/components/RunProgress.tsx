import { Icon } from "@/components/Icon";
import { PREVIEW_STEPS } from "@/lib/preview";

export function RunProgress({ step }: { step: number }) {
  return <section className="panel progress-panel" aria-labelledby="progress-title"><span className="eyebrow">SYNTHETIC WORKFLOW PREVIEW</span><h1 id="progress-title">A considered conclusion takes a few steps.</h1><p>No model or data source is being called. This animation previews how a future analysis will progress.</p><ol className="progress-steps">{PREVIEW_STEPS.map((label, index) => <li className={index < step ? "done" : index === step ? "current" : ""} key={label}><span className="step-marker">{index < step ? <Icon name="check" size={15} /> : index + 1}</span><span>{label}</span>{index === step && <span className="spinner" aria-hidden="true" />}</li>)}</ol><p className="sr-only" role="status" aria-live="polite">{PREVIEW_STEPS[Math.min(step, PREVIEW_STEPS.length - 1)]}</p></section>;
}
