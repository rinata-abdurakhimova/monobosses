"""Show how the pipeline is wired to the modules of R3/R4/R5. Run from services/api:
    python scripts/check_wiring.py
Paste its output to R2 when a function is missing or a signature differs."""

from vic import modules
from vic.prompts import available_prompts


def main() -> int:
    found = modules.discover()
    ok = True
    print("== Functions (contract section 4)")
    for name, expected in modules.EXPECTED_PARAMS.items():
        items = found[name]
        if not items:
            note = "optional (R2-03)" if name not in modules.REQUIRED else "MISSING"
            ok = ok and name not in modules.REQUIRED
            print(f"  {name:<22} {note}")
            continue
        mod, fn = items[0]
        params = modules.positional_names(fn)
        compatible = modules.compatible_signature(name, fn)
        flag = "OK" if compatible else f"SIGNATURE DIFFERS: has {params}, contract says {expected}"
        ok = ok and compatible
        extra = f"  (also in: {', '.join(m for m, _ in items[1:])})" if len(items) > 1 else ""
        print(f"  {name:<22} {mod}  [{flag}]{extra}")
    print("\n== Prompts (prompt_id -> version)")
    for pid, version in available_prompts().items():
        print(f"  {pid:<12} {version or 'NOT FOUND'}")
    if modules.IMPORT_ERRORS:
        print("\n== Import errors")
        for name, err in modules.IMPORT_ERRORS.items():
            print(f"  {name}: {err}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
