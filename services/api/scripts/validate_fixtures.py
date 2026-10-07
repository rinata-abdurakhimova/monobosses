"""Validate every committed fixture with Pydantic + integrity checks.

Usage (from services/api):  python scripts/validate_fixtures.py   (exit code 1 on failure)
"""
import json
import sys
from pathlib import Path

from vic import integrity
from vic.contracts import CaseInput, EvidencePack, Report, Run

FIXTURES = Path(__file__).resolve().parents[3] / "contracts" / "fixtures"
MODELS = {"case": CaseInput, "evidence-pack": EvidencePack, "report-v1": Report,
          "report-v2": Report, "run-running": Run, "run-failed": Run}


def main() -> int:
    ok = True
    loaded = {}
    for stem, model in MODELS.items():
        path = FIXTURES / f"{stem}.json"
        try:
            obj = model.model_validate(json.loads(path.read_text(encoding="utf-8")))
            problems: list[str] = []
            if isinstance(obj, Report):
                problems = integrity.check_report(obj)
            elif isinstance(obj, EvidencePack):
                problems = integrity.check_evidence_pack(obj)
            loaded[stem] = obj
            if problems:
                raise ValueError("; ".join(problems))
            print(f"OK    {stem}.json")
        except Exception as exc:  # noqa: BLE001
            ok = False
            print(f"FAIL  {stem}.json: {exc}")
    if "report-v1" in loaded and "report-v2" in loaded:
        problems = integrity.check_revision(loaded["report-v1"], loaded["report-v2"])
        for p in problems:
            ok = False
            print(f"FAIL  revision v1->v2: {p}")
        if not problems:
            print("OK    revision v1 -> v2")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())