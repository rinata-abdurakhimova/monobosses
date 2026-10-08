"""Print the stored trace of a run (no secrets are stored). From services/api:
    python scripts/show_trace.py run-XXXXXXXX"""
import json
import sys

from vic.storage import get_repository


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) != 2:
        print("usage: python scripts/show_trace.py <run_id>")
        return 2
    trace = get_repository().get_trace(sys.argv[1])
    if trace is None:
        print("no trace for this run (it may still be running)")
        return 1
    print(json.dumps(trace, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
