type Analysis = {
  position: string;
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
  if (analysis.position === "insufficient_data") {
    return {
      label: "Evidence gaps — conclusion incomplete",
      explanation:
        "Read the analysis below for findings, proposed next steps and the evidence still needed. This position does not mean the node produced no information.",
    };
  }
  return { label: analysis.position.replaceAll("_", " "), explanation: null };
}
