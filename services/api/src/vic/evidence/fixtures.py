"""Build EvidencePacks from contracts/fixtures/synthetic-docs/*.json.

baseline = docs 01-04 (report v1); safety update = doc 05 (the "new evidence" for v2).
R2's own contracts/fixtures/evidence-pack.json is NOT touched by this module.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from .importer import ImportResult, build_pack, parse_json, verify_pack

REPO_ROOT = Path(__file__).resolve().parents[5]
SYNTHETIC_DIR = REPO_ROOT / "contracts" / "fixtures" / "synthetic-docs"
FIXED_RETRIEVED_AT = datetime(2025, 1, 1, tzinfo=timezone.utc)  # synthetic constant


def _load(pattern: str) -> ImportResult:
    paths = sorted(SYNTHETIC_DIR.glob(pattern))
    if not paths:
        raise FileNotFoundError(f"No synthetic documents match {pattern} in {SYNTHETIC_DIR}")
    result = build_pack([parse_json(p.read_bytes()) for p in paths], retrieved_at=FIXED_RETRIEVED_AT)
    problems = verify_pack(result)
    if problems:
        raise AssertionError("Synthetic fixture failed verification: " + "; ".join(problems))
    return result


def build_baseline_pack() -> ImportResult:
    return _load("0[1-4]-*.json")


def build_safety_update_pack() -> ImportResult:
    return _load("05-*.json")
