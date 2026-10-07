"""Repository abstraction + in-memory implementation seeded with synthetic fixtures.

R2-01 ships ONLY the in-memory repository (data is lost on restart).
R2-02 adds a SQLite implementation behind the same `Repository` interface.
"""
import hashlib
import threading
import uuid
from datetime import UTC, datetime
from functools import lru_cache
from typing import Protocol

from vic import synthetic
from vic.contracts import CaseInput, Evidence, EvidenceCreate, EvidenceCreated, Report, Run, Source


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


class ReportExistsError(ValueError):
    """A report version is immutable: it can be saved once and never overwritten."""


class Repository(Protocol):
    def ping(self) -> None: ...
    def create_case(self, case: CaseInput) -> str: ...
    def get_case(self, case_id: str) -> CaseInput | None: ...
    def create_run(self, run: Run) -> None: ...
    def get_run(self, run_id: str) -> Run | None: ...
    def update_run(self, run: Run) -> None: ...
    def save_report(self, report: Report) -> None: ...
    def get_report(self, case_id: str, version: int) -> Report | None: ...
    def get_report_by_id(self, report_id: str) -> Report | None: ...
    def list_reports(self, case_id: str) -> list[Report]: ...
    def add_evidence(self, case_id: str, payload: EvidenceCreate) -> EvidenceCreated: ...


class InMemoryRepository:
    def __init__(self, seed: bool = True):
        self._lock = threading.RLock()
        self._cases: dict[str, CaseInput] = {}
        self._runs: dict[str, Run] = {}
        self._reports: dict[tuple[str, int], Report] = {}
        self._sources: dict[str, list[Source]] = {}
        self._evidence: dict[str, list[Evidence]] = {}
        if seed:
            self._seed()

    def _seed(self) -> None:
        built = synthetic.build_all()
        self._cases[synthetic.CASE_ID] = built["case"]
        for key in ("report-v1", "report-v2"):
            self.save_report(built[key])
        for key in ("run-running", "run-failed"):
            self.create_run(built[key])

    def ping(self) -> None:
        return None  # an in-memory store is always available

    def create_case(self, case: CaseInput) -> str:
        with self._lock:
            case_id = new_id("case")
            self._cases[case_id] = case.model_copy(deep=True)
            return case_id

    def get_case(self, case_id: str) -> CaseInput | None:
        with self._lock:
            case = self._cases.get(case_id)
            return case.model_copy(deep=True) if case else None

    def create_run(self, run: Run) -> None:
        with self._lock:
            self._runs[run.id] = run.model_copy(deep=True)

    def get_run(self, run_id: str) -> Run | None:
        with self._lock:
            run = self._runs.get(run_id)
            return run.model_copy(deep=True) if run else None

    def update_run(self, run: Run) -> None:
        with self._lock:
            if run.id not in self._runs:
                raise KeyError(run.id)
            self._runs[run.id] = run.model_copy(deep=True)

    def save_report(self, report: Report) -> None:
        with self._lock:
            key = (report.case_id, report.version)
            if key in self._reports:
                raise ReportExistsError(f"report {report.case_id} v{report.version} already exists")
            self._reports[key] = report.model_copy(deep=True)

    def get_report(self, case_id: str, version: int) -> Report | None:
        with self._lock:
            report = self._reports.get((case_id, version))
            return report.model_copy(deep=True) if report else None

    def get_report_by_id(self, report_id: str) -> Report | None:
        with self._lock:
            for report in self._reports.values():
                if report.id == report_id:
                    return report.model_copy(deep=True)
            return None

    def list_reports(self, case_id: str) -> list[Report]:
        with self._lock:
            found = [r for (cid, _), r in self._reports.items() if cid == case_id]
            return [r.model_copy(deep=True) for r in sorted(found, key=lambda r: r.version)]

    def add_evidence(self, case_id: str, payload: EvidenceCreate) -> EvidenceCreated:
        # R2-01: the whole text is stored as one excerpt. Real chunking/provenance is R3's job.
        with self._lock:
            case = self._cases[case_id]
            source_id, evidence_id = new_id("src"), new_id("ev")
            digest = hashlib.sha256(payload.text.encode("utf-8")).hexdigest()
            self._sources.setdefault(case_id, []).append(Source(
                id=source_id, title=payload.title, url=None, type="user_upload",
                published_at=payload.published_at, retrieved_at=datetime.now(UTC),
                content_hash=f"sha256:{digest}", synthetic=payload.synthetic))
            self._evidence.setdefault(case_id, []).append(Evidence(
                id=evidence_id, source_id=source_id, excerpt=payload.text, locator="text",
                scope=case.scope, limitations=[]))
            return EvidenceCreated(source_id=source_id, evidence_ids=[evidence_id])


@lru_cache
def get_repository() -> InMemoryRepository:
    return InMemoryRepository()