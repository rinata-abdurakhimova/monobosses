"""Resolve the functions of R3/R4/R5 (contract section 4) or the synthetic dev stubs.

Real functions are discovered by NAME inside vic.evidence and vic.agents, so the pipeline does
not depend on which file each role put them in. `scripts/check_wiring.py` prints what was found.

Synthetic development mode: DEV_STUBS=true stubs everything; DEV_STUBS=true together with
STUB_MODULES=<names> stubs only those functions and runs the real ones for the rest.
"""
import asyncio
import importlib
import inspect
import pkgutil
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from vic.config import Settings
from vic.failures import ModuleNotReady

STUB_ORIGIN = "vic.stubs"

# Positional parameter names of each function. analyze_clinical follows what R4 implemented
# (two separate RoleResults); the pipeline also accepts the older list form (see call_clinical).
EXPECTED_PARAMS: dict[str, list[str]] = {
    "build_evidence_pack": ["case", "ctx"],
    "import_document": ["document", "ctx"],
    "audit_claims": ["claims", "pack", "ctx"],
    "analyze_science": ["case", "pack", "ctx"],
    "analyze_translation": ["case", "pack", "ctx"],
    "analyze_clinical": ["case", "pack", "scientific_result", "translation_result", "ctx"],
    "analyze_market": ["case", "pack", "ctx"],
    "analyze_investment": ["case", "pack", "clinical", "market", "ctx"],
    "analyze_ip_licensing": ["case", "pack", "ctx"],
    "analyze_partnerships": ["case", "pack", "ctx"],
    "analyze_investment_threshold": ["case", "pack", "ctx"],
    "analyze_failure_miner": ["case", "pack", "ctx"],
    "synthesize_committee": ["results", "audit", "ctx"],
}
# import_document is used by the PDF upload route (R2-03), not by the pipeline.
REQUIRED = [n for n in EXPECTED_PARAMS if n != "import_document"]
ROOTS = ["vic.evidence", "vic.agents"]

IMPORT_ERRORS: dict[str, str] = {}


@dataclass
class Modules:
    build_evidence_pack: Callable[..., Any] | None = None
    import_document: Callable[..., Any] | None = None
    audit_claims: Callable[..., Any] | None = None
    analyze_science: Callable[..., Any] | None = None
    analyze_translation: Callable[..., Any] | None = None
    analyze_clinical: Callable[..., Any] | None = None
    analyze_market: Callable[..., Any] | None = None
    analyze_investment: Callable[..., Any] | None = None
    analyze_ip_licensing: Callable[..., Any] | None = None
    analyze_partnerships: Callable[..., Any] | None = None
    analyze_investment_threshold: Callable[..., Any] | None = None
    analyze_failure_miner: Callable[..., Any] | None = None
    synthesize_committee: Callable[..., Any] | None = None
    origin: dict[str, str] = field(default_factory=dict)  # function name -> module path

    def missing(self) -> list[str]:
        return [n for n in REQUIRED if getattr(self, n) is None]


def positional_names(fn: Callable[..., Any]) -> list[str]:
    """Names of the positional parameters (keyword-only extras such as `scenarios=` are ignored)."""
    kinds = (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
    return [p.name for p in inspect.signature(fn).parameters.values() if p.kind in kinds]


def call_clinical(fn: Callable[..., Any], case, pack, science, translation, ctx):
    """R4 implemented analyze_clinical(case, pack, scientific_result, translation_result, ctx);
    the contract text says analyze_clinical(case, pack, scientific: list, ctx). Support both."""
    names = positional_names(fn)
    if "translation_result" in names or len(names) >= 5:
        return fn(case, pack, science, translation, ctx)
    return fn(case, pack, [science, translation], ctx)


def call_investment(fn: Callable[..., Any], case, pack, clinical, market, ctx, **upstream):
    if positional_names(fn) == ["case", "pack", "ctx"]:
        accepted = inspect.signature(fn).parameters
        extras = {key: value for key, value in upstream.items() if key in accepted}
        return fn(case, pack, ctx, clinical=clinical, market=market, **extras)
    return fn(case, pack, clinical, market, ctx)


async def call_audit(fn: Callable[..., Any], claims, pack, ctx, *, documents=None):
    args = (claims, pack, ctx) if "ctx" in inspect.signature(fn).parameters else (claims, pack)
    kwargs = {"documents": documents} if "documents" in inspect.signature(fn).parameters else {}
    if inspect.iscoroutinefunction(fn):
        return await fn(*args, **kwargs)
    return await asyncio.to_thread(fn, *args, **kwargs)


def compatible_signature(name: str, fn: Callable[..., Any]) -> bool:
    params = positional_names(fn)
    alternatives = {
        "audit_claims": [["claims", "pack"]],
        "analyze_investment": [["case", "pack", "ctx"]],
        "analyze_clinical": [["case", "pack", "scientific", "ctx"]],
    }
    return params in [EXPECTED_PARAMS[name], *alternatives.get(name, [])]


def _walk(root: str):
    try:
        package = importlib.import_module(root)
    except Exception as exc:  # noqa: BLE001
        IMPORT_ERRORS[root] = f"{type(exc).__name__}: {exc}"
        return
    yield package
    path = getattr(package, "__path__", None)
    if not path:
        return
    for info in pkgutil.walk_packages(path, prefix=root + ".", onerror=lambda n: None):
        leaf = info.name.rsplit(".", 1)[-1]
        if leaf.startswith("test") or leaf == "__main__":
            continue
        try:
            yield importlib.import_module(info.name)
        except Exception as exc:  # noqa: BLE001
            IMPORT_ERRORS[info.name] = f"{type(exc).__name__}: {exc}"


def discover() -> dict[str, list[tuple[str, Callable[..., Any]]]]:
    """function name -> [(module, function)] for every candidate found (defined-in-module first)."""
    IMPORT_ERRORS.clear()
    found: dict[str, list[tuple[str, Callable[..., Any]]]] = {n: [] for n in EXPECTED_PARAMS}
    for root in ROOTS:
        for module in _walk(root):
            for name in EXPECTED_PARAMS:
                fn = getattr(module, name, None)
                if callable(fn) and (inspect.iscoroutinefunction(fn) or name == "audit_claims"):
                    found[name].append((module.__name__, fn))
    for items in found.values():
        items.sort(key=lambda it: getattr(it[1], "__module__", "") != it[0])  # defined here first
    # Explicit adapters select the semantic audit and bridge the rich Chair API.
    try:
        from vic.committee import synthesize_committee
        from vic.evidence.audit_semantic import audit_claims_semantic
        found["audit_claims"].insert(0, ("vic.evidence.audit_semantic", audit_claims_semantic))
        found["synthesize_committee"] = [("vic.committee", synthesize_committee)]
    except ImportError as exc:
        IMPORT_ERRORS["vic.committee"] = str(exc)
    return found


def resolve_real(required=None) -> Modules:
    found = discover()
    mods = Modules()
    for name, items in found.items():
        if items:
            setattr(mods, name, items[0][1])
            mods.origin[name] = items[0][0]
    missing = [name for name in (REQUIRED if required is None else required) if getattr(mods, name) is None]
    if missing:
        detail = "; ".join(f"{k}: {v}" for k, v in IMPORT_ERRORS.items())
        raise ModuleNotReady("Required functions are not available yet: " + ", ".join(missing)
                             + (f". Import errors: {detail}" if detail else ""))
    return mods


def get_modules(settings: Settings) -> Modules:
    excluded = {'analyze_investment_threshold', 'analyze_failure_miner', 'audit_claims', 'synthesize_committee'} if settings.short_committee else set()
    required = [name for name in REQUIRED if name not in excluded]
    if not settings.dev_stubs:
        return resolve_real(required)
    from vic.stubs import make_stub_modules

    wanted = settings.stub_module_set  # empty = stub everything
    real_agents = bool(wanted) and any(n.startswith("analyze_") and n not in wanted for n in REQUIRED)
    stubs = make_stub_modules(use_r3_fixtures=real_agents)
    found = discover() if wanted else {}
    mods, missing = Modules(), []
    for name in required:
        if not wanted or name in wanted:
            setattr(mods, name, getattr(stubs, name))
            mods.origin[name] = STUB_ORIGIN
        elif found.get(name):
            setattr(mods, name, found[name][0][1])
            mods.origin[name] = found[name][0][0]
        else:
            missing.append(name)
    if missing:
        raise ModuleNotReady("Not available yet (add them to STUB_MODULES or wait for their owner): "
                             + ", ".join(missing))
    unknown = sorted(n for n in wanted if n not in REQUIRED)
    if unknown:
        raise ModuleNotReady("Unknown names in STUB_MODULES: " + ", ".join(unknown))
    return mods
