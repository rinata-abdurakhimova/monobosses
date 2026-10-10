const hiddenRoles = new Set(["investment_threshold", "failure_miner", "audit"]);
export function isVisibleRole(id: string) {
  return !hiddenRoles.has(id);
}
