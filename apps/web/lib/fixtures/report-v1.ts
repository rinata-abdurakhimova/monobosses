import report from "../../../../contracts/fixtures/report-v1.json" with { type: "json" };
import caseInput from "../../../../contracts/fixtures/case.json" with { type: "json" };
import { mapSyntheticReport } from "../contracts/report.ts";

// R2's shared fixture is the single source of truth; input never changes it.
export const reportV1 = mapSyntheticReport(report, caseInput);
