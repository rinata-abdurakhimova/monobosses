import type { Report } from "./types";
import type { Claim } from "./contracts/generated";

function claimSnapshot(claim: Claim) {
  return JSON.stringify([
    claim.id,
    claim.text,
    claim.scope,
    claim.provenance,
    claim.support_status,
    claim.importance,
    [...(claim.evidence_ids ?? [])].sort(),
    claim.assumptions ?? [],
  ]);
}

/** A comparison must use the actual parent, never an arbitrary prior version. */
export function validateRevisionPair(before: Report, after: Report): void {
  const revision = after.contract.revision;
  if (
    !revision ||
    revision.parent_report_id !== before.id ||
    before.contract.case_id !== after.contract.case_id ||
    before.version >= after.version ||
    revision.previous_recommendation !== before.recommendation ||
    revision.new_recommendation !== after.recommendation
  )
    throw new Error("The revision does not match this parent report.");
  for (const change of revision.changed_claims) {
    for (const [claimed, report] of [
      [change.before, before],
      [change.after, after],
    ] as const) {
      const actual = report.claims.find((c) => c.id === change.claim_id);
      if (
        claimed
          ? claimed.id !== change.claim_id ||
            !actual ||
            claimSnapshot(claimed) !== claimSnapshot(actual)
          : !!actual
      )
        throw new Error("Changed claims do not match the saved reports.");
    }
  }
  const changedIds = revision.changed_claims.map((change) => change.claim_id);
  const allIds = new Set(
    [...before.claims, ...after.claims].map((claim) => claim.id),
  );
  const actualChangedIds = [...allIds].filter((id) => {
    const oldClaim = before.claims.find((claim) => claim.id === id);
    const newClaim = after.claims.find((claim) => claim.id === id);
    return (
      !oldClaim ||
      !newClaim ||
      claimSnapshot(oldClaim) !== claimSnapshot(newClaim)
    );
  });
  if (
    new Set(changedIds).size !== changedIds.length ||
    changedIds.length !== actualChangedIds.length ||
    actualChangedIds.some((id) => !changedIds.includes(id))
  )
    throw new Error(
      "The revision's changed claims are incomplete or duplicated.",
    );
  if (
    revision.new_evidence_ids.some(
      (id) =>
        !after.evidence.some((e) => e.id === id) ||
        before.evidence.some((e) => e.id === id),
    )
  )
    throw new Error("New evidence does not match the saved reports.");
}

export function reportVersionUrl(caseId: string, version: number): string {
  return `/cases/${encodeURIComponent(caseId)}?flow=api&version=${version}`;
}
