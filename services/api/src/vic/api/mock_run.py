"""MOCK run creation (R2-01 only). Replaced by the real background pipeline in R2-02.

A mock run never analyzes anything: it copies the synthetic fixture report into the case
and returns a completed run that is clearly labelled as mock.
"""
from vic import integrity, synthetic
from vic.contracts import Report, Run, RunCreate, RunStage, RunStatus, Usage
from vic.errors import ApiError
from vic.storage import Repository, new_id

MOCK_WARNING = "MOCK: synthetic fixture report; no real analysis was performed"


def create_mock_run(repo: Repository, case_id: str, body: RunCreate) -> Run:
    existing = repo.list_reports(case_id)
    parent: Report | None = None
    if body.parent_report_id:
        parent = repo.get_report_by_id(body.parent_report_id)
        if parent is None:
            raise ApiError(404, "not_found", f"Report '{body.parent_report_id}' not found")
        if parent.case_id != case_id:
            raise ApiError(409, "incompatible_parent_report",
                           "parent_report_id belongs to a different case")

    if parent is None:
        if existing:
            raise ApiError(409, "mock_limitation",
                           "Mock mode: this case already has reports; pass parent_report_id of v1")
        template, version = synthetic.build_report(1), 1
    else:
        if parent.version != 1 or len(existing) != 1:
            raise ApiError(409, "mock_limitation",
                           "Mock mode supports only a v1 -> v2 revision per case")
        template, version = synthetic.build_report(2), 2

    run_id, report_id = new_id("run"), new_id("rep")
    update = {"id": report_id, "case_id": case_id, "run_id": run_id}
    if parent is not None and template.revision is not None:
        update["revision"] = template.revision.model_copy(update={"parent_report_id": parent.id})
    report = template.model_copy(update=update)
    integrity.assert_report(report, parent=parent)
    repo.save_report(report)

    run = Run(id=run_id, case_id=case_id, status=RunStatus.COMPLETED, stage=RunStage.FINALIZE,
              report_version=version, warnings=[MOCK_WARNING], trace_id=new_id("trace"),
              usage=Usage(), latency_ms={}, cost_usd=None, model_version="mock",
              config_version="mock-v1", mode=body.mode, parent_report_id=body.parent_report_id)
    repo.create_run(run)
    return run