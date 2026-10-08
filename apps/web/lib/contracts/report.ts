import type {
  Report as ContractReport,
  CaseInput as ContractCase,
  RoleId,
} from "./generated";
import type { Report, SectionKey, ReportSection } from "../types";
import { validateContract } from "./validate.ts";

export const SECTION_TITLES: Record<SectionKey, string> = {
  recommendation: "Committee recommendation",
  scientific_thesis: "Scientific thesis",
  human_translation_thesis: "Human translation thesis",
  clinical_development_plan: "Clinical development plan",
  competitive_landscape: "Competitive landscape",
  commercial_opportunity: "Commercial opportunity",
  capital_to_milestone: "Capital to milestone",
  key_risks: "Key risks",
  critical_unknowns: "Critical unknowns",
  diligence_questions: "Diligence questions",
  sources: "Sources",
};

const ROLE_NAMES: Record<RoleId, [string, string]> = {
  science: ["Scientific perspective", "SC"],
  translation: ["Human translation", "HT"],
  clinical: ["Clinical development", "CL"],
  market: ["Market and commercial opportunity", "MK"],
  investment: ["Finance and investment scenarios", "IN"],
  chair: ["Committee chair", "CH"],
  audit: ["Evidence audit", "AU"],
  failure_miner: ["Critical risks and failure modes", "FM"],
  investment_threshold: ["Investment conditions", "IT"],
  partnerships: ["Partnerships", "PA"],
  ip_licensing: ["Intellectual property and licensing", "IP"],
};

function roleName(id: string): [string, string] {
  return Object.hasOwn(ROLE_NAMES, id)
    ? ROLE_NAMES[id as RoleId]
    : [`Additional perspective (${id})`, "AI"];
}

/** Fixture previews require synthetic data and the fixture's own input. */
export function mapSyntheticReport(raw: unknown, rawCase: unknown): Report {
  const result = mapApiReport(raw);
  validateContract("CaseInput", rawCase);
  const input = rawCase as ContractCase;
  if (!result.synthetic || result.sources.some((s) => !s.synthetic))
    throw new Error("The preview requires a wholly synthetic report");
  if (result.scope !== input.scope)
    throw new Error("Fixture scope does not match its case");
  return { ...result, title: `${input.indication} · ${input.mechanism}` };
}

/** Map the received report, preserving its scope and synthetic flags. */
export function mapApiReport(raw: unknown): Report {
  validateContract("Report", raw, { allowUnknownRoles: true });
  const report = raw as ContractReport;
  const keys = Object.keys(SECTION_TITLES) as SectionKey[];
  if (
    report.sections.length !== keys.length ||
    keys.some(
      (key) =>
        report.sections.filter((section) => section.key === key).length !== 1,
    )
  ) {
    throw new Error("The report requires all 11 sections exactly once");
  }
  function unique(values: string[], name: string): Set<string> {
    if (new Set(values).size !== values.length)
      throw new Error(`Duplicate ${name} IDs`);
    return new Set(values);
  }
  const sourceIds = unique(
    report.sources.map((s) => s.id),
    "source",
  );
  const evidenceIds = unique(
    report.evidence.map((e) => e.id),
    "evidence",
  );
  const claimIds = unique(
    report.claims.map((c) => c.id),
    "claim",
  );
  function references(ids: string[], known: Set<string>): void {
    if (ids.some((id) => !known.has(id)))
      throw new Error("Dangling report reference");
  }
  report.evidence.forEach((e) => references([e.source_id], sourceIds));
  report.claims.forEach((c) => {
    references(c.evidence_ids ?? [], evidenceIds);
    if (
      (c.provenance === "source" ||
        ["supported", "contradicted", "mixed"].includes(c.support_status)) &&
      !c.evidence_ids?.length
    )
      throw new Error("An evidence-backed claim requires evidence IDs");
  });
  report.sections.forEach((s) => references(s.claim_ids ?? [], claimIds));
  (report.risks ?? []).forEach((r) => references(r.claim_ids ?? [], claimIds));
  for (const role of report.roles) {
    references(
      (role.claims ?? []).map((c) => c.id),
      claimIds,
    );
    (role.claims ?? []).forEach((claim) =>
      references(claim.evidence_ids ?? [], evidenceIds),
    );
    (role.section_content ?? []).forEach((s) =>
      references(s.claim_ids ?? [], claimIds),
    );
    (role.risks ?? []).forEach((r) => references(r.claim_ids ?? [], claimIds));
  }
  const claims = report.claims.map((c) => ({
    ...c,
    evidence_ids: c.evidence_ids ?? [],
    assumptions: c.assumptions ?? [],
  }));
  return {
    contract: report,
    id: report.id,
    version: report.version,
    title: report.synthetic
      ? "Synthetic assessment example"
      : "Saved assessment",
    recommendation: report.recommendation,
    scope: report.scope,
    synthetic: report.synthetic,
    rationale: report.rationale,
    conditions: report.decision_conditions ?? [],
    claims,
    evidence: report.evidence,
    sources: report.sources.map((s) => ({
      ...s,
      available: true,
      limitation:
        [
          ...new Set(
            report.evidence
              .filter((e) => e.source_id === s.id)
              .flatMap((e) => e.limitations ?? []),
          ),
        ].join(" ") ||
        (s.synthetic
          ? "Fictional source from a synthetic report."
          : "No additional source limitations reported."),
    })),
    roles: report.roles.map((role) => ({
      id: role.role_id,
      name: roleName(role.role_id)[0],
      initials: roleName(role.role_id)[1],
      summary: role.summary,
      position: role.position,
      claims: (role.claims ?? []).map((c) => ({
        ...c,
        evidence_ids: c.evidence_ids ?? [],
        assumptions: c.assumptions ?? [],
      })),
      risks: role.risks ?? [],
      unknowns: role.unknowns ?? [],
      change_conditions: role.change_conditions ?? [],
      section_content: role.section_content ?? [],
      unknown:
        (role.unknowns ?? []).join("; ") || "No additional unknowns reported.",
    })),
    risks: (report.risks ?? []).map((r) => ({
      id: r.id,
      title: r.description,
      priority:
        r.priority === "critical"
          ? "Critical"
          : r.priority === "minor"
            ? "Minor"
            : "Material",
      impact: r.impact,
      next_check: r.next_check,
    })),
    unknowns: [...new Set(report.roles.flatMap((r) => r.unknowns ?? []))],
    diligence_questions: report.diligence_questions.map((q) => ({
      question: q.question,
      why: q.why_it_matters,
      evidence_needed: q.evidence_needed,
      positive: q.decision_if_positive,
      negative: q.decision_if_negative,
    })),
    disagreements:
      (report.disagreements ?? [])
        .map((d) => `${d.topic}: ${d.summary} ${d.resolution}`)
        .join("\n") || "No disagreements reported.",
    sections: keys.map((key) => {
      const section = report.sections.find((s) => s.key === key)!;
      const linked = claims.filter((c) => section.claim_ids?.includes(c.id));
      let status: ReportSection["status"] = report.synthetic
        ? "Illustrative plan"
        : "Reported plan";
      if (linked.some((c) => c.support_status === "contradicted"))
        status = report.synthetic ? "Contradicted in sample" : "Contradicted";
      else if (
        linked.some((c) => ["unknown", "unverified"].includes(c.support_status))
      )
        status = "Data needed";
      else if (linked.some((c) => c.support_status === "mixed"))
        status = "Uncertain";
      else if (linked.length)
        status = report.synthetic ? "Supported in sample" : "Supported";
      return {
        key,
        title: SECTION_TITLES[key],
        summary: section.summary,
        status,
        points: [],
        claim_ids: section.claim_ids ?? [],
        limitation: section.limitations?.join(" "),
      };
    }),
  };
}
