"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Icon } from "@/components/Icon";
import { sampleInput, savePreviewCase } from "@/lib/preview";
import type { CaseInput, PreviewMode, Scope } from "@/lib/types";
import { createMockApiClient } from "@/lib/api";
import { asApiError } from "@/lib/api/errors";
import { MOCK_SCENARIOS, type MockScenario } from "@/lib/api/types";

const empty: CaseInput = {
  indication: "",
  mechanism: "",
  scope: "approach",
  modality: "",
  development_stage: "",
  program_data: "",
};
export function CaseForm() {
  const router = useRouter();
  const [input, setInput] = useState<CaseInput>(empty);
  const [mode, setMode] = useState<PreviewMode>("complete");
  const [flow, setFlow] = useState<"fixture" | "mock-api">("fixture");
  const [mockScenario, setMockScenario] = useState<MockScenario>("complete");
  const [errors, setErrors] = useState<
    Partial<Record<keyof CaseInput, string>>
  >({});
  const [storageError, setStorageError] = useState("");
  const [busy, setBusy] = useState(false);
  const submitted = useRef(false);
  const request = useRef<AbortController | null>(null);
  useEffect(() => () => request.current?.abort(), []);
  function update<K extends keyof CaseInput>(key: K, value: CaseInput[K]) {
    setInput((previous) => ({ ...previous, [key]: value }));
    setErrors((previous) => ({ ...previous, [key]: undefined }));
  }
  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const next: typeof errors = {};
    if (!input.indication.trim())
      next.indication = "Enter an indication or disease.";
    if (!input.mechanism.trim())
      next.mechanism = "Enter a mechanism or biological target.";
    if (input.scope === "program" && input.program_data.trim().length < 40)
      next.program_data =
        "Add at least 40 characters of programme data, or select an approach assessment.";
    setErrors(next);
    if (Object.keys(next).length) {
      document.getElementById(Object.keys(next)[0])?.focus();
      return;
    }
    if (submitted.current) return;
    submitted.current = true;
    setBusy(true);
    setStorageError("");
    const controller = new AbortController();
    request.current = controller;
    try {
      const normalizedInput = {
        ...input,
        indication: input.indication.trim(),
        mechanism: input.mechanism.trim(),
      };
      if (flow === "mock-api") {
        const client = createMockApiClient({ scenario: mockScenario });
        const created = await client.createCase(normalizedInput, {
          signal: controller.signal,
        });
        const started = await client.startRun(created.case_id, {
          signal: controller.signal,
        });
        if (!controller.signal.aborted)
          router.push(
            `/cases/${encodeURIComponent(created.case_id)}?flow=mock-api&run=${encodeURIComponent(started.run_id)}`,
          );
        return;
      }
      const id = savePreviewCase(normalizedInput, mode);
      router.push(`/cases/${id}`);
    } catch (failure) {
      if (controller.signal.aborted) return;
      submitted.current = false;
      setBusy(false);
      if (flow === "mock-api") {
        const error = asApiError(failure);
        setStorageError(error.message);
        setErrors(error.fieldErrors);
        const field = Object.keys(error.fieldErrors)[0];
        if (field) document.getElementById(field)?.focus();
      } else
        setStorageError(
          "The preview could not be saved in this browser. Enable session storage, or open the example report.",
        );
    }
  }
  return (
    <form
      className="panel case-form"
      onSubmit={submit}
      noValidate
    >
      <div className="panel-heading">
        <div>
          <span className="eyebrow">THE STARTING POINT</span>
          <h2>Your investment thesis</h2>
        </div>
        <span className="tiny-tag">01 / Input</span>
      </div>
      <fieldset className="scope-field">
        <legend>What are you assessing?</legend>
        <div className="scope-options">
          {(["approach", "program"] as Scope[]).map((scope) => (
            <label
              className={`scope-option ${input.scope === scope ? "selected" : ""}`}
              key={scope}
            >
              <input
                type="radio"
                name="scope"
                value={scope}
                checked={input.scope === scope}
                onChange={() => update("scope", scope)}
              />
              <span>
                <strong>
                  {scope === "approach"
                    ? "A biological approach"
                    : "A specific programme"}
                </strong>
                <small>
                  {scope === "approach"
                    ? "Start with a disease and a mechanism"
                    : "Include candidate-specific evidence"}
                </small>
              </span>
            </label>
          ))}
        </div>
      </fieldset>
      <div className="field workflow-select">
        <label htmlFor="workflow">Preview workflow</label>
        <select
          id="workflow"
          value={flow}
          onChange={(event) => {
            setFlow(event.target.value as "fixture" | "mock-api");
            setStorageError("");
            setErrors({});
          }}
          disabled={busy}
        >
          <option value="fixture">Fixed fictional report preview</option>
          <option value="mock-api">Mock API workflow — local simulation</option>
        </select>
        <small>
          The Python API is not connected. These workflows use separate local
          data stores.
        </small>
      </div>
      <div className="form-fields">
        <div className="field">
          <label htmlFor="indication">
            Indication <span>Required</span>
          </label>
          <input
            id="indication"
            value={input.indication}
            onChange={(e) => update("indication", e.target.value)}
            placeholder="Disease or patient population"
            maxLength={240}
            required
            aria-invalid={!!errors.indication}
            aria-describedby={
              errors.indication ? "indication-error" : undefined
            }
          />
          {errors.indication && (
            <p
              id="indication-error"
              className="field-error"
            >
              {errors.indication}
            </p>
          )}
        </div>
        <div className="field">
          <label htmlFor="mechanism">
            Mechanism / target <span>Required</span>
          </label>
          <input
            id="mechanism"
            value={input.mechanism}
            onChange={(e) => update("mechanism", e.target.value)}
            placeholder="Biological target or mechanism of action"
            maxLength={240}
            required
            aria-invalid={!!errors.mechanism}
            aria-describedby={
              errors.mechanism ? "mechanism-error" : "mechanism-help"
            }
          />
          <small id="mechanism-help">
            A drug name is not required to assess an approach.
          </small>
          {errors.mechanism && (
            <p
              id="mechanism-error"
              className="field-error"
            >
              {errors.mechanism}
            </p>
          )}
        </div>
      </div>
      <details
        className="additional-details"
        open={input.scope === "program" ? true : undefined}
      >
        <summary>
          Additional context <span>Optional for an approach</span>
          <Icon
            name="chevron"
            size={16}
          />
        </summary>
        <div className="optional-fields">
          <div className="field">
            <label htmlFor="modality">Modality</label>
            <select
              id="modality"
              value={input.modality}
              onChange={(e) => update("modality", e.target.value)}
            >
              <option value="">Not specified</option>
              {[
                ...new Set([
                  "Small molecule",
                  "Antibody",
                  "Gene therapy",
                  "Cell therapy",
                  "RNA therapy",
                  "Other",
                  input.modality,
                ]),
              ]
                .filter(Boolean)
                .map((x) => (
                  <option key={x}>{x}</option>
                ))}
            </select>
          </div>
          <div className="field">
            <label htmlFor="development-stage">Development stage</label>
            <select
              id="development-stage"
              value={input.development_stage}
              onChange={(e) => update("development_stage", e.target.value)}
            >
              <option value="">Not specified</option>
              {[
                ...new Set([
                  "Discovery",
                  "Preclinical",
                  "Phase 1",
                  "Phase 2",
                  "Phase 3",
                  input.development_stage,
                ]),
              ]
                .filter(Boolean)
                .map((x) => (
                  <option key={x}>{x}</option>
                ))}
            </select>
          </div>
          <div className="field span-two">
            <label htmlFor="program_data">
              Programme data{" "}
              {input.scope === "program" && <span>Required</span>}
            </label>
            <textarea
              id="program_data"
              value={input.program_data}
              onChange={(e) => update("program_data", e.target.value)}
              rows={4}
              placeholder="Candidate details, available results, biomarkers, or route of administration"
              maxLength={5000}
              aria-invalid={!!errors.program_data}
              aria-describedby={
                errors.program_data ? "program-error" : undefined
              }
            />
            {errors.program_data && (
              <p
                id="program-error"
                className="field-error"
              >
                {errors.program_data}
              </p>
            )}
          </div>
        </div>
      </details>
      <div className="form-notice">
        <Icon
          name="flask"
          size={18}
        />
        <p>
          {flow === "mock-api"
            ? "This mock API workflow opens a "
            : "This preview opens a "}
          <strong>fixed fictional report</strong>. Your input is saved locally
          for the interface flow; it is not analysed or sent to a model.
        </p>
      </div>
      <details className="preview-settings">
        <summary>Preview states</summary>
        {flow === "mock-api" ? (
          <>
            <label htmlFor="mock-scenario">Choose a mock API scenario</label>
            <select
              id="mock-scenario"
              value={mockScenario}
              onChange={(event) =>
                setMockScenario(event.target.value as MockScenario)
              }
              disabled={busy}
            >
              {MOCK_SCENARIOS.map((scenario) => (
                <option
                  key={scenario.value}
                  value={scenario.value}
                >
                  {scenario.label}
                </option>
              ))}
            </select>
          </>
        ) : (
          <>
            <label htmlFor="preview-mode">Choose a UI scenario</label>
            <select
              id="preview-mode"
              value={mode}
              onChange={(e) => setMode(e.target.value as PreviewMode)}
            >
              <option value="complete">Completed sample report</option>
              <option value="failed">Simulated failed run</option>
              <option value="unavailable">
                Sample with an unavailable source
              </option>
            </select>
          </>
        )}
      </details>
      {storageError && (
        <p
          className="field-error"
          role="alert"
        >
          {storageError}
        </p>
      )}
      {Object.keys(errors).length > 0 && (
        <p
          className="sr-only"
          role="alert"
        >
          Please correct the highlighted fields.
        </p>
      )}
      <div className="form-actions">
        <button
          className="button button-primary"
          type="submit"
          disabled={busy}
        >
          {busy
            ? "Opening preview…"
            : flow === "mock-api"
              ? "Start mock workflow"
              : "Preview assessment"}
          <Icon
            name="arrow"
            size={18}
          />
        </button>
        <button
          className="button button-text"
          type="button"
          onClick={() => {
            setInput({ ...sampleInput });
            setErrors({});
          }}
        >
          Use fictional example
        </button>
      </div>
    </form>
  );
}
