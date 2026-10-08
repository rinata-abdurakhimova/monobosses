"""SQLite repository (R2-02). One connection per operation, so it is safe across threads.

Reports are immutable (SQL triggers) and versions are allocated inside one IMMEDIATE
transaction. Durability requires DATABASE_URL to point at a persistent volume.
"""
import hashlib
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Callable, Iterator, Protocol

from vic import synthetic
from vic.config import get_settings
from vic.contracts import (CaseInput, ErrorBody, Evidence, EvidenceCreate, EvidenceCreated,
                           EvidencePack, Report, Run, RunStatus, Source)

_SEED_RUN_IDS = ("run-synthetic-running", "run-synthetic-failed")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS cases(
  id TEXT PRIMARY KEY, data TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS runs(
  id TEXT PRIMARY KEY, case_id TEXT NOT NULL, status TEXT NOT NULL, data TEXT NOT NULL,
  trace TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_runs_status ON runs(status);
CREATE TABLE IF NOT EXISTS snapshots(
  id TEXT PRIMARY KEY, case_id TEXT NOT NULL, data TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS reports(
  id TEXT PRIMARY KEY, case_id TEXT NOT NULL, version INTEGER NOT NULL, data TEXT NOT NULL,
  created_at TEXT NOT NULL, UNIQUE(case_id, version));
CREATE TRIGGER IF NOT EXISTS reports_no_update BEFORE UPDATE ON reports
  BEGIN SELECT RAISE(ABORT, 'reports are immutable'); END;
CREATE TRIGGER IF NOT EXISTS reports_no_delete BEFORE DELETE ON reports
  BEGIN SELECT RAISE(ABORT, 'reports are immutable'); END;
CREATE TABLE IF NOT EXISTS user_sources(
  case_id TEXT NOT NULL, source_id TEXT NOT NULL, data TEXT NOT NULL,
  PRIMARY KEY(case_id, source_id));
CREATE TABLE IF NOT EXISTS user_evidence(
  case_id TEXT NOT NULL, evidence_id TEXT NOT NULL, data TEXT NOT NULL,
  PRIMARY KEY(case_id, evidence_id));
"""


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ReportExistsError(ValueError):
    """A report version is immutable: it can be saved once and never overwritten."""


class SnapshotExistsError(ValueError):
    """Snapshots are immutable too."""


class Repository(Protocol):
    def startup(self) -> int: ...
    def ping(self) -> None: ...
    def create_case(self, case: CaseInput) -> str: ...
    def get_case(self, case_id: str) -> CaseInput | None: ...
    def create_run(self, run: Run) -> None: ...
    def get_run(self, run_id: str) -> Run | None: ...
    def update_run(self, run: Run) -> None: ...
    def save_trace(self, run_id: str, trace: dict) -> None: ...
    def get_trace(self, run_id: str) -> dict | None: ...
    def count_active_runs(self, case_id: str | None = None) -> int: ...
    def save_snapshot(self, case_id: str, pack: EvidencePack) -> None: ...
    def get_snapshot(self, snapshot_id: str) -> EvidencePack | None: ...
    def save_report(self, report: Report) -> None: ...
    def save_next_report(self, case_id: str, factory: Callable[[int], Report]) -> Report: ...
    def get_report(self, case_id: str, version: int) -> Report | None: ...
    def get_report_by_id(self, report_id: str) -> Report | None: ...
    def get_latest_report(self, case_id: str) -> Report | None: ...
    def list_reports(self, case_id: str) -> list[Report]: ...
    def add_evidence(self, case_id: str, payload: EvidenceCreate) -> EvidenceCreated: ...
    def list_user_evidence(self, case_id: str) -> tuple[list[Source], list[Evidence]]: ...


class SqliteRepository:
    def __init__(self, path: str, seed: bool = True):
        if path == ":memory:":
            raise ValueError("use a file path: every connection would get its own empty database")
        self.path = path
        self._seed_enabled = seed
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path, timeout=30)
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript(_SCHEMA)
            conn.commit()
        finally:
            conn.close()

    @contextmanager
    def _tx(self, immediate: bool = False) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        try:
            conn.execute("BEGIN IMMEDIATE" if immediate else "BEGIN")
            yield conn
            conn.execute("COMMIT")
        except BaseException:
            try:
                conn.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise
        finally:
            conn.close()

    # ------------------------------------------------------------ lifecycle
    def startup(self) -> int:
        """Recover interrupted runs FIRST, then seed fixtures. Returns the number recovered."""
        recovered = self.recover_interrupted_runs()
        if self._seed_enabled:
            self._seed()
        return recovered

    def ping(self) -> None:
        with self._tx() as c:
            c.execute("SELECT 1").fetchone()

    def recover_interrupted_runs(self) -> int:
        """A run that was queued/running when the process died can never finish: fail it."""
        count = 0
        with self._tx(immediate=True) as c:
            rows = c.execute("SELECT id, data FROM runs WHERE status IN ('queued','running')").fetchall()
            for run_id, data in rows:
                if run_id in _SEED_RUN_IDS:
                    continue
                run = Run.model_validate_json(data)
                run = run.model_copy(update={
                    "status": RunStatus.FAILED,
                    "error": ErrorBody(code="run_interrupted", retryable=True,
                                       message="The server restarted while this run was in "
                                               "progress. Start the run again."),
                    "warnings": [*run.warnings, "Run was interrupted by a server restart"],
                })
                c.execute("UPDATE runs SET status=?, data=?, updated_at=? WHERE id=?",
                          (run.status.value, run.model_dump_json(), _now(), run_id))
                count += 1
        return count

    def _seed(self) -> None:
        built = synthetic.build_all()
        now = _now()
        with self._tx(immediate=True) as c:
            c.execute("INSERT OR IGNORE INTO cases(id,data,created_at) VALUES(?,?,?)",
                      (synthetic.CASE_ID, built["case"].model_dump_json(), now))
            for key in ("report-v1", "report-v2"):
                r = built[key]
                c.execute("INSERT OR IGNORE INTO reports(id,case_id,version,data,created_at) "
                          "VALUES(?,?,?,?,?)", (r.id, r.case_id, r.version, r.model_dump_json(), now))
            for key in ("run-running", "run-failed"):
                run = built[key]
                c.execute("INSERT OR REPLACE INTO runs(id,case_id,status,data,trace,created_at,"
                          "updated_at) VALUES(?,?,?,?,NULL,?,?)",
                          (run.id, run.case_id, run.status.value, run.model_dump_json(), now, now))

    # ------------------------------------------------------------ cases
    def create_case(self, case: CaseInput) -> str:
        case_id = new_id("case")
        with self._tx(immediate=True) as c:
            c.execute("INSERT INTO cases(id,data,created_at) VALUES(?,?,?)",
                      (case_id, case.model_dump_json(), _now()))
        return case_id

    def get_case(self, case_id: str) -> CaseInput | None:
        with self._tx() as c:
            row = c.execute("SELECT data FROM cases WHERE id=?", (case_id,)).fetchone()
        return CaseInput.model_validate_json(row[0]) if row else None

    # ------------------------------------------------------------ runs
    def create_run(self, run: Run) -> None:
        now = _now()
        with self._tx(immediate=True) as c:
            c.execute("INSERT OR REPLACE INTO runs(id,case_id,status,data,trace,created_at,"
                      "updated_at) VALUES(?,?,?,?,NULL,?,?)",
                      (run.id, run.case_id, run.status.value, run.model_dump_json(), now, now))

    def get_run(self, run_id: str) -> Run | None:
        with self._tx() as c:
            row = c.execute("SELECT data FROM runs WHERE id=?", (run_id,)).fetchone()
        return Run.model_validate_json(row[0]) if row else None

    def update_run(self, run: Run) -> None:
        with self._tx(immediate=True) as c:
            cur = c.execute("UPDATE runs SET status=?, data=?, updated_at=? WHERE id=?",
                            (run.status.value, run.model_dump_json(), _now(), run.id))
            if cur.rowcount == 0:
                raise KeyError(run.id)

    def save_trace(self, run_id: str, trace: dict) -> None:
        import json
        with self._tx(immediate=True) as c:
            c.execute("UPDATE runs SET trace=? WHERE id=?",
                      (json.dumps(trace, ensure_ascii=False, default=str), run_id))

    def get_trace(self, run_id: str) -> dict | None:
        import json
        with self._tx() as c:
            row = c.execute("SELECT trace FROM runs WHERE id=?", (run_id,)).fetchone()
        return json.loads(row[0]) if row and row[0] else None

    def count_active_runs(self, case_id: str | None = None) -> int:
        marks = ",".join("?" for _ in _SEED_RUN_IDS)
        sql = ("SELECT COUNT(*) FROM runs WHERE status IN ('queued','running') "
               f"AND id NOT IN ({marks})")
        params: list = list(_SEED_RUN_IDS)
        if case_id is not None:
            sql += " AND case_id=?"
            params.append(case_id)
        with self._tx() as c:
            return c.execute(sql, params).fetchone()[0]

    # ------------------------------------------------------------ snapshots
    def save_snapshot(self, case_id: str, pack: EvidencePack) -> None:
        try:
            with self._tx(immediate=True) as c:
                c.execute("INSERT INTO snapshots(id,case_id,data,created_at) VALUES(?,?,?,?)",
                          (pack.snapshot_id, case_id, pack.model_dump_json(), _now()))
        except sqlite3.IntegrityError as exc:
            raise SnapshotExistsError(f"snapshot {pack.snapshot_id} already exists") from exc

    def get_snapshot(self, snapshot_id: str) -> EvidencePack | None:
        with self._tx() as c:
            row = c.execute("SELECT data FROM snapshots WHERE id=?", (snapshot_id,)).fetchone()
        return EvidencePack.model_validate_json(row[0]) if row else None

    # ------------------------------------------------------------ reports
    def save_report(self, report: Report) -> None:
        """Save a report whose version is already decided (seeding, mock runs)."""
        try:
            with self._tx(immediate=True) as c:
                c.execute("INSERT INTO reports(id,case_id,version,data,created_at) VALUES(?,?,?,?,?)",
                          (report.id, report.case_id, report.version, report.model_dump_json(), _now()))
        except sqlite3.IntegrityError as exc:
            raise ReportExistsError(f"report {report.case_id} v{report.version} already exists") from exc

    def save_next_report(self, case_id: str, factory: Callable[[int], Report]) -> Report:
        """Allocate the next version atomically. `factory` runs INSIDE the write lock:
        keep it fast and do not touch the repository from it."""
        with self._tx(immediate=True) as c:
            version = c.execute("SELECT COALESCE(MAX(version),0)+1 FROM reports WHERE case_id=?",
                                (case_id,)).fetchone()[0]
            report = factory(version)
            if report.version != version or report.case_id != case_id:
                raise ValueError("factory returned a report with the wrong version or case_id")
            try:
                c.execute("INSERT INTO reports(id,case_id,version,data,created_at) VALUES(?,?,?,?,?)",
                          (report.id, report.case_id, report.version, report.model_dump_json(), _now()))
            except sqlite3.IntegrityError as exc:
                raise ReportExistsError(f"report {case_id} v{version} already exists") from exc
        return report

    def get_report(self, case_id: str, version: int) -> Report | None:
        with self._tx() as c:
            row = c.execute("SELECT data FROM reports WHERE case_id=? AND version=?",
                            (case_id, version)).fetchone()
        return Report.model_validate_json(row[0]) if row else None

    def get_report_by_id(self, report_id: str) -> Report | None:
        with self._tx() as c:
            row = c.execute("SELECT data FROM reports WHERE id=?", (report_id,)).fetchone()
        return Report.model_validate_json(row[0]) if row else None

    def get_latest_report(self, case_id: str) -> Report | None:
        with self._tx() as c:
            row = c.execute("SELECT data FROM reports WHERE case_id=? ORDER BY version DESC LIMIT 1",
                            (case_id,)).fetchone()
        return Report.model_validate_json(row[0]) if row else None

    def list_reports(self, case_id: str) -> list[Report]:
        with self._tx() as c:
            rows = c.execute("SELECT data FROM reports WHERE case_id=? ORDER BY version",
                             (case_id,)).fetchall()
        return [Report.model_validate_json(r[0]) for r in rows]

    # ------------------------------------------------------------ user evidence
    def add_evidence(self, case_id: str, payload: EvidenceCreate) -> EvidenceCreated:
        # The whole text is ONE excerpt for now; real chunking/provenance is R3's job.
        with self._tx(immediate=True) as c:
            row = c.execute("SELECT data FROM cases WHERE id=?", (case_id,)).fetchone()
            if row is None:
                raise KeyError(case_id)
            case = CaseInput.model_validate_json(row[0])
            source_id, evidence_id = new_id("src"), new_id("ev")
            digest = hashlib.sha256(payload.text.encode("utf-8")).hexdigest()
            source = Source(id=source_id, title=payload.title, url=None, type="user_upload",
                            published_at=payload.published_at, retrieved_at=datetime.now(timezone.utc),
                            content_hash=f"sha256:{digest}", synthetic=payload.synthetic)
            evidence = Evidence(id=evidence_id, source_id=source_id, excerpt=payload.text,
                                locator="text", scope=case.scope, limitations=[])
            c.execute("INSERT INTO user_sources(case_id,source_id,data) VALUES(?,?,?)",
                      (case_id, source_id, source.model_dump_json()))
            c.execute("INSERT INTO user_evidence(case_id,evidence_id,data) VALUES(?,?,?)",
                      (case_id, evidence_id, evidence.model_dump_json()))
        return EvidenceCreated(source_id=source_id, evidence_ids=[evidence_id])

    def list_user_evidence(self, case_id: str) -> tuple[list[Source], list[Evidence]]:
        with self._tx() as c:
            s = c.execute("SELECT data FROM user_sources WHERE case_id=? ORDER BY rowid",
                          (case_id,)).fetchall()
            e = c.execute("SELECT data FROM user_evidence WHERE case_id=? ORDER BY rowid",
                          (case_id,)).fetchall()
        return ([Source.model_validate_json(r[0]) for r in s],
                [Evidence.model_validate_json(r[0]) for r in e])


@lru_cache
def get_repository() -> SqliteRepository:
    settings = get_settings()
    return SqliteRepository(settings.sqlite_path, seed=settings.seed_synthetic)