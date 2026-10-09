"""Frozen evidence-only evaluation using the same pipeline as HTTP.

python evals/run.py manifest.json --output artifacts/evaluation
Expectations and identity maps stay outside model payloads.
"""
import argparse
import asyncio
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from vic.config import Settings
from vic.contracts import CaseInput, EvidencePack, Run, RunMode, RunStatus
from vic.evidence.importer import ImportResult, build_pack, parse_json
from vic.llm import build_llm
from vic.modules import get_modules
from vic.pipeline import Pipeline
from vic.storage import SqliteRepository, new_id


def read_value(value, root):
    return json.loads((root / value).read_text(encoding="utf-8")) if isinstance(value, str) else value


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def validate_manifest(manifest):
    rows = manifest["cases"]
    ids, families = set(), {}
    for row in rows:
        if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,100}", row["id"]) or row["id"] in ids:
            raise ValueError("Case IDs must be unique safe file names")
        if row["split"] not in ("development", "holdout"):
            raise ValueError("Case split must be development or holdout")
        if families.setdefault(row["family"], row["split"]) != row["split"]:
            raise ValueError("Related case families must stay in the same split")
        if row.get("parent") and row["parent"] not in ids:
            raise ValueError("Paired parent must precede its revision")
        ids.add(row["id"])
    if not rows:
        raise ValueError("Manifest has no cases")
    return rows


async def evaluate(manifest_path: Path, output: Path, settings: Settings):
    rows = validate_manifest(json.loads(manifest_path.read_text(encoding="utf-8")))
    output = output / new_id("evaluation")
    output.mkdir(parents=True, exist_ok=True)
    repo = SqliteRepository(str(output / "results.sqlite3"), seed=False)
    print(f"Results: {output}", flush=True)
    repo.startup()
    summary, completed = [], {}
    for row in rows:
        directory = output / row["id"]
        directory.mkdir(exist_ok=True)
        case = CaseInput.model_validate(read_value(row["input"], manifest_path.parent))
        parent = None
        if row.get("parent"):
            if row["parent"] not in completed:
                raise ValueError("Cannot revise a failed evaluation case")
            case_id, parent, family = completed[row["parent"]]
            if repo.get_case(case_id) != case or family != row["family"]:
                raise ValueError("Paired revision must use the same input and family")
        else:
            case_id = repo.create_case(case)
        data = read_value(row["pack"], manifest_path.parent)
        if "documents" in data:
            imported = build_pack([parse_json(document) for document in data["documents"]])
        else:
            imported = ImportResult(EvidencePack.model_validate(data), [], datetime.now(timezone.utc))
        repo.add_import(case_id, imported)
        run = Run(id=new_id("run"), case_id=case_id, status=RunStatus.QUEUED,
                  trace_id=new_id("trace"), mode=RunMode.EVIDENCE_ONLY,
                  parent_report_id=parent.id if parent else None)
        repo.create_run(run)
        pipeline = Pipeline(repo, settings, lambda: get_modules(settings), lambda: build_llm(settings))
        result = await pipeline.execute(run)
        write_json(directory / "run.json", result.model_dump(mode="json"))
        write_json(directory / "trace.json", repo.get_trace(run.id))
        write_json(directory / "manifest.json", row)
        report = None
        if result.report_version is not None:
            report = repo.get_report(case_id, result.report_version)
            write_json(directory / "report.json", report.model_dump(mode="json"))
            write_json(directory / "snapshot.json", repo.get_snapshot(report.snapshot_id).model_dump(mode="json"))
            completed[row["id"]] = (case_id, report, row["family"])
        summary.append(dict(id=row["id"], family=row["family"], split=row["split"],
            status=result.status.value, error=result.error.model_dump(mode="json") if result.error else None,
            recommendation=report.recommendation.value if report else None,
            latency_ms=result.latency_ms, usage=result.usage.model_dump(mode="json"), cost_usd=result.cost_usd))
        write_json(output / "summary.json", summary)
    write_json(output / "config.json", settings.public_config())
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    summary = asyncio.run(evaluate(args.manifest, args.output, Settings()))
    failures = sum(item["status"] != "completed" for item in summary)
    print(f"Cases: {len(summary)}, completed: {len(summary) - failures}, failed: {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
