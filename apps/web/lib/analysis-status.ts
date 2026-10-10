type Analysis = {
  position: string;
  role_id?: string;
  id?: string;
  claims?: { support_status: string; evidence_ids?: string[] }[];
  section_content?: { structured_data?: unknown }[];
};

export function analysisStatus(analysis: Analysis) {
  const recovery = analysis.section_content?.some((section) => {
    const data = section.structured_data;
    if (!data || typeof data !== "object" || !("node_recovery" in data)) {
      return false;
    }
    const value = data.node_recovery;
    return (
      value != null &&
      typeof value === "object" &&
      "status" in value &&
      value.status === "analysis_unavailable"
    );
  });
  if (recovery) {
    return {
      label: "Analysis unavailable — output rejected",
      explanation:
        "The specialist output failed validation. This is an analysis error, not a finding that evidence is absent.",
    };
  }
  const hasFindings = analysis.claims?.some(
    (claim) =>
      ["supported", "mixed", "contradicted"].includes(claim.support_status) &&
      (claim.evidence_ids?.length ?? 0) > 0,
  );
  const partialLegacy =
    analysis.position === "insufficient_data" &&
    ["clinical", "market", "partnerships"].includes(
      analysis.role_id ?? analysis.id ?? "",
    ) &&
    hasFindings;
  if (analysis.position === "partial_assessment" || partialLegacy) {
    return {
      label: "Preliminary conclusions from available evidence",
      explanation:
        "The findings below support a partial assessment. Specific evidence gaps and decision conditions remain open.",
    };
  }
  if (analysis.position === "insufficient_data") {
    return {
      label: "Evidence gaps — conclusion incomplete",
      explanation:
        "Read the analysis below for findings, proposed next steps and the evidence still needed. This position does not mean the node produced no information.",
    };
  }
  return { label: analysis.position.replaceAll("_", " "), explanation: null };
}

export function visibleFindings<
  T extends { support_status: string; evidence_ids?: string[] },
>(claims: T[] | undefined) {
  const rank = (claim: T) =>
    ["supported", "mixed", "contradicted"].includes(claim.support_status) &&
    (claim.evidence_ids?.length ?? 0) > 0
      ? 0
      : 1;
  return [...(claims ?? [])].sort((a, b) => rank(a) - rank(b)).slice(0, 4);
}
