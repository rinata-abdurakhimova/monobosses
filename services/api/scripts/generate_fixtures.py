"""Write contracts/fixtures/*.json from vic.synthetic (the single source of truth).

Usage (from services/api):  python scripts/generate_fixtures.py
"""
import json
from pathlib import Path

from vic.synthetic import build_all

ROOT = Path(__file__).resolve().parents[3]  # repo root
OUT = ROOT / "contracts" / "fixtures"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for stem, model in build_all().items():  # build_all validates models + integrity
        path = OUT / f"{stem}.json"
        path.write_text(json.dumps(model.model_dump(mode="json"), indent=2, ensure_ascii=False)
                        + "\n", encoding="utf-8")
        print(f"wrote {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()