"""Exercise HTTP -> all nodes -> saved report, optionally PDF -> explicit revision.

Uses a clearly synthetic case with real model calls in evidence-only mode.
Start the API with RUN_BACKEND=pipeline and DEV_STUBS=false first.
The base URL can also be the frontend's /api/backend proxy.
"""
import argparse
import json
import time
from pathlib import Path

import httpx
from vic.contracts import Report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--revision", action="store_true")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    from vic.config import Settings
    secret = Settings().api_shared_secret
    headers = {"X-API-Key": secret} if secret else {}
    # Same-origin header allows exercising the frontend mutation proxy.
    origin = str(httpx.URL(args.base_url).copy_with(path="")) .rstrip("/")
    headers["Origin"] = origin
    with httpx.Client(base_url=args.base_url.rstrip("/") + "/", headers=headers, timeout=30) as client:
        def request(method, path, **kwargs):
            response = client.request(method, path, **kwargs)
            if response.status_code >= 400:
                raise RuntimeError(f"HTTP {response.status_code} on {path}")
            return response.json()
        case = dict(indication="Synthetic disease X", mechanism="Inhibition of synthetic target Y",
            scope="program", modality="Oral small molecule", development_stage="Preclinical",
            program_data="SYN-X is a fictional oral inhibitor of target Y. Only animal efficacy is available; human exposure, safety, clinical benefit and programme budget remain unknown.",
            as_of_date="2026-10-09")
        case_id = request("POST", "cases", json=case)["case_id"]
        request("POST", f"cases/{case_id}/evidence", json=dict(title="Synthetic baseline",
            text="SYNTHETIC: SYN-X inhibited target Y and reduced a disease marker in mice. No human exposure, safety or patient-benefit study is available. No programme budget, patent ownership, licensing rights, partner interest or pricing has been established.",
            published_at="2026-10-01", synthetic=True))

        def analyze(parent=None):
            run_id = request("POST", f"cases/{case_id}/runs", json=dict(mode="evidence_only",
                parent_report_id=parent.id if parent else None))["run_id"]
            deadline, stage = time.monotonic() + 700, None
            while time.monotonic() < deadline:
                run = request("GET", f"runs/{run_id}")
                if run.get("stage") != stage:
                    stage = run.get("stage")
                    print(f"{run_id}: {run['status']} / {stage}", flush=True)
                if run["status"] in ("completed", "failed"):
                    (args.output / f"{run_id}.json").write_text(json.dumps(run, indent=2), encoding="utf-8")
                    if run["status"] == "failed":
                        print(f"FAILED: {run['error']['code']}: {run['error']['message']}", flush=True)
                        return None
                    report = Report.model_validate(request("GET", f"cases/{case_id}/reports/{run['report_version']}"))
                    assert len(report.sections) == 11
                    expected = {"science", "translation", "clinical", "market", "investment", "ip_licensing",
                                "partnerships", "investment_threshold", "failure_miner", "chair", "audit"}
                    assert {role.role_id.value for role in report.roles} == expected
                    (args.output / f"report-v{report.version}.json").write_text(report.model_dump_json(indent=2), encoding="utf-8")
                    assert request("GET", f"cases/{case_id}/reports/{report.version}")["run_id"] == run_id
                    print(f"PASS: v{report.version}, {len(report.roles)} roles, 11 sections, {report.recommendation.value}", flush=True)
                    return report
                time.sleep(2)
            raise RuntimeError("Workflow exceeded polling deadline")
        first = analyze()
        if first is None:
            return 1
        if args.revision:
            from tests.vic.evidence.pdf_helpers import make_pdf
            pdf = make_pdf([["SYNTHETIC: A human exposure study of SYN-X recorded serious liver toxicity at the exposure required for target engagement. This directly challenges the safe-exposure premise for SYN-X, not every inhibitor of target Y."]])
            imported = request("POST", f"cases/{case_id}/documents", files={"file": ("safety.pdf", pdf, "application/pdf")},
                data={"title": "Synthetic decisive safety update", "synthetic": "true", "published_at": "2026-10-08", "scope": "program"})
            assert request("GET", f"cases/{case_id}/reports/1")["id"] == first.id
            second = analyze(first)
            if second is None:
                return 1
            assert second.revision.parent_report_id == first.id
            assert set(imported["evidence_ids"]) <= set(second.revision.new_evidence_ids)
            assert request("GET", f"cases/{case_id}/reports/1") == first.model_dump(mode="json")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
