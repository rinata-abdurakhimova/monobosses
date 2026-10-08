import report from "../../../../contracts/fixtures/report-r5.json" with { type: "json" };
import caseInput from "../../../../contracts/fixtures/case.json" with { type: "json" };
import { mapSyntheticReport } from "../contracts/report.ts";

// Display fixture for all agreed perspectives; no live expert nodes are executed.
export const reportR5 = mapSyntheticReport(report, caseInput);
