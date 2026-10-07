"""Export the OpenAPI schema to contracts/openapi.json.

Usage (from services/api):  python scripts/export_openapi.py
"""
import json
from pathlib import Path

from vic.main import app

OUT = Path(__file__).resolve().parents[3] / "contracts" / "openapi.json"


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(app.openapi(), indent=2, ensure_ascii=False, sort_keys=True) + "\n",
                   encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()