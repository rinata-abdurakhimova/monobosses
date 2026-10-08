"""R3-03 (part C): identity anonymization, leakage scan, temporal flags, blind-guess record.

Honest by design: the report says `controlled_as_tested` only when every check passed, and even
then carries the standing limitations. Anything unproven is `partial` or `uncontrolled`.
The evaluator mapping (original ids / names) is returned SEPARATELY and must never reach the model.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import date

from pydantic import BaseModel, Field

from vic.contracts import EvidencePack, RunContext, Source

BLIND_GUESS_PROMPT_ID = "blind_guess"  # prompt text: evidence/prompts/blind_guess.md (R2 must register it)

_DIRECT = [
    (re.compile(r"https?://\S+|www\.\S+", re.I), "[URL]"),
    (re.compile(r"\b10\.\d{4,9}/\S+", re.I), "[DOI]"),
    (re.compile(r"\bPMID:?\s*\d{5,9}\b", re.I), "[PMID]"),
    (re.compile(r"\bNCT\d{8}\b", re.I), "[TRIAL_ID]"),
    (re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"), "[EMAIL]"),
]
_CODE = re.compile(r"\b[A-Z][A-Z0-9]{0,5}-?\d{1,5}[A-Z]?\b")  # compound / trial codes: LIB003, X-001, SYN1

STANDING_LIMITATIONS = [
    "A failed blind identity guess does not guarantee protection: the model may still recognise the case "
    "from facts that were not masked.",
    "A publication date after a model's release date does not prove the facts were unseen; only a "
    "documented training cutoff earlier than the outcome supports that.",
    "An obscure drug or small company does not mean the case is unseen by the model.",
    "Masking is rule-based (listed names + ID patterns); indirect identifiers such as dates, numbers and "
    "design details can remain.",
]


# ------------------------------------------------------------------ anonymization

@dataclass
class EvaluatorMapping:
    """Keep OUT of any model input and out of the public repo if it names real programs."""

    source_ids: dict[str, str] = field(default_factory=dict)    # original -> blind
    evidence_ids: dict[str, str] = field(default_factory=dict)  # original -> blind
    placeholders: dict[str, str] = field(default_factory=dict)  # real name -> placeholder
    original_titles: dict[str, str] = field(default_factory=dict)  # blind source id -> original title


@dataclass
class BlindResult:
    pack: EvidencePack
    mapping: EvaluatorMapping
    replaced: dict[str, int]
    residual_risks: list[str]


def _letters(i: int) -> str:
    return chr(65 + i) if i < 26 else f"A{i}"


def _term_regex(term: str) -> re.Pattern:
    return re.compile(r"(?<![A-Za-z0-9])" + re.escape(term) + r"(?![A-Za-z0-9])", re.I)


def anonymize_pack(pack: EvidencePack, identity_terms: list[str]) -> BlindResult:
    """Mask identity_terms (drug, company, trial names), scrub direct IDs, re-key all ids."""
    terms = sorted({t.strip() for t in identity_terms if t and t.strip()}, key=len, reverse=True)
    placeholders = {t: f"[NAME_{_letters(i)}]" for i, t in enumerate(terms)}
    patterns = {t: _term_regex(t) for t in terms}
    counts = {t: 0 for t in terms}

    def scrub(text: str) -> str:
        for pat, repl in _DIRECT:
            text = pat.sub(repl, text)
        for t in terms:
            text, n = patterns[t].subn(placeholders[t], text)
            counts[t] += n
        return text

    mapping = EvaluatorMapping(placeholders=placeholders)
    blind_titles: dict[str, str] = {}
    for n, src in enumerate(pack.sources, start=1):
        bid = f"blind-src-{n:02d}"
        mapping.source_ids[src.id] = bid
        mapping.original_titles[bid] = src.title
        blind_titles[src.title] = f"Source {n:02d} ({src.type})"

    evidence = []
    for n, ev in enumerate(pack.evidence, start=1):
        mapping.evidence_ids[ev.id] = f"blind-ev-{n:03d}"
        evidence.append(ev.model_copy(update=dict(
            id=mapping.evidence_ids[ev.id],
            source_id=mapping.source_ids.get(ev.source_id, "blind-src-unknown"),
            excerpt=scrub(ev.excerpt),
            locator=scrub(ev.locator),
            limitations=[scrub(x) for x in ev.limitations],
        )))

    sources: list[Source] = []
    for src in pack.sources:
        bid = mapping.source_ids[src.id]
        text = "\n".join(e.excerpt for e in evidence if e.source_id == bid)
        sources.append(src.model_copy(update=dict(
            id=bid, title=blind_titles[src.title], url=None, document_id=None,
            content_hash="sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest(),
        )))

    warnings = []
    for w in pack.retrieval_warnings:
        for original, blind in blind_titles.items():
            w = w.replace(original, blind)
        warnings.append(scrub(w))
    digest = hashlib.sha256("|".join(s.content_hash for s in sources).encode()).hexdigest()[:12]
    blind_pack = pack.model_copy(update=dict(
        sources=sources, evidence=evidence, retrieval_warnings=warnings, snapshot_id=f"snap-blind-{digest}"))

    dated = sum(1 for s in sources if s.published_at)
    risks = [
        f"{dated} source(s) keep their publication date (needed for temporal control); dates can act as indirect identifiers.",
        "Numbers, sample sizes and design details were kept and can identify a well-known study.",
        "Only the supplied identity_terms and ID patterns are masked; unlisted names are not.",
    ]
    return BlindResult(pack=blind_pack, mapping=mapping, replaced=counts, residual_risks=risks)


# ------------------------------------------------------------------ leakage scan

@dataclass(frozen=True)
class LeakFinding:
    kind: str    # identity_term | direct_id | possible_code
    where: str
    detail: str


def _texts(pack: EvidencePack):
    for s in pack.sources:
        yield f"title of {s.id}", s.title
    for e in pack.evidence:
        yield f"excerpt {e.id}", e.excerpt
        yield f"locator {e.id}", e.locator
        for i, lim in enumerate(e.limitations):
            yield f"limitation {i + 1} of {e.id}", lim
    for i, w in enumerate(pack.retrieval_warnings):
        yield f"warning {i + 1}", w


def scan_blind_pack(
    pack: EvidencePack, identity_terms: list[str], allow_terms: list[str] | None = None
) -> list[LeakFinding]:
    """Look for what anonymization should have removed. Empty list = no leak DETECTED (not proven absent).

    `allow_terms`: legitimate tokens that look like codes (e.g. the mechanism "JAK1") and must stay.
    """
    allowed = {a.upper() for a in (allow_terms or [])}
    findings: list[LeakFinding] = []
    seen: set[tuple[str, str]] = set()

    def add(kind: str, where: str, detail: str) -> None:
        if (kind, detail) not in seen:
            seen.add((kind, detail))
            findings.append(LeakFinding(kind, where, detail))

    for s in pack.sources:
        if s.url:
            add("direct_id", f"url of {s.id}", s.url)
        if s.document_id:
            add("direct_id", f"document_id of {s.id}", s.document_id)
    patterns = {t: _term_regex(t) for t in identity_terms if t and t.strip()}
    for where, text in _texts(pack):
        for t, pat in patterns.items():
            if pat.search(text):
                add("identity_term", where, t)
        for pat, _ in _DIRECT:
            m = pat.search(text)
            if m:
                add("direct_id", where, m.group(0)[:60])
        for m in _CODE.finditer(text):
            if m.group(0).upper() not in allowed:
                add("possible_code", where, m.group(0))
    return findings


# ------------------------------------------------------------------ temporal flags

@dataclass
class TemporalAssessment:
    control_level: str  # controlled | partially_controlled | uncontrolled
    flags: list[str]


def assess_temporal(
    sources: list[Source],
    *,
    as_of: date | None,
    model_cutoff: date | None = None,
    cutoff_documented: bool = False,
    outcome_date: date | None = None,
) -> TemporalAssessment:
    """`controlled` only when: evidence is clean w.r.t. as_of, the model cutoff is DOCUMENTED and the
    outcome came after it. A model release date is not a documented cutoff."""
    if as_of is None:
        return TemporalAssessment("uncontrolled", [
            "No as_of_date: the case is not temporally restricted, so leakage of later outcomes is not controlled."])
    flags: list[str] = []
    hard = soft = False
    for s in sources:
        if s.published_at is None:
            soft = True
            flags.append(f"Source {s.id} has no publication date; its availability at as_of_date is uncertain.")
        elif s.published_at > as_of:
            hard = True
            flags.append(f"after_as_of: source {s.id} was published {s.published_at}, after as_of_date {as_of}.")
        elif s.type == "registry":
            soft = True
            flags.append(f"Source {s.id} is a registry record; its current version may contain information "
                         "posted after as_of_date (use a frozen version).")
    if not cutoff_documented or model_cutoff is None:
        soft = True
        flags.append("The model's training cutoff is not documented: leakage through the model's own "
                     "knowledge is NOT controlled.")
    elif outcome_date is None:
        soft = True
        flags.append("The outcome date is not recorded; cannot compare it with the model's training cutoff.")
    elif outcome_date <= model_cutoff:
        soft = True
        flags.append(f"The outcome ({outcome_date}) is not after the documented model cutoff ({model_cutoff}): "
                     "the model may have seen it.")
    level = "uncontrolled" if hard else ("partially_controlled" if soft else "controlled")
    return TemporalAssessment(level, flags)


# ------------------------------------------------------------------ blind guess

class BlindGuess(BaseModel):
    candidate_names: list[str] = Field(default_factory=list,
        description="Drug, company or program names you think this evidence describes; empty if you cannot tell")
    confidence: str = Field(description="low, medium or high")
    reasoning: str = Field(description="Which facts in the evidence made you think so")


@dataclass
class BlindGuessResult:
    performed: bool
    identified: bool
    matched_terms: list[str]
    guesser: str
    confidence: str | None = None
    note: str = ""


def evaluate_blind_guess(
    guess: list[str] | str, identity_terms: list[str], *, guesser: str, confidence: str | None = None
) -> BlindGuessResult:
    text = guess.lower() if isinstance(guess, str) else " | ".join(guess).lower()
    matched = [t for t in identity_terms if t.strip() and t.lower() in text]
    return BlindGuessResult(
        performed=True, identified=bool(matched), matched_terms=matched, guesser=guesser,
        confidence=confidence,
        note="Re-identified: leakage failure." if matched else "Not re-identified; this does not prove protection.")


async def blind_identity_guess(blind: BlindResult, identity_terms: list[str], ctx: RunContext) -> BlindGuessResult:
    """Ask the model to guess identity from the blind pack ONLY (no mapping, no original titles)."""
    if ctx.model is None:
        return BlindGuessResult(False, False, [], "none", note="No LLM adapter: blind guess not performed.")
    srcs = {s.id: s for s in blind.pack.sources}
    items = "\n\n".join(
        f"[{e.id}] ({srcs[e.source_id].type if e.source_id in srcs else 'unknown'}) {e.excerpt}"
        for e in blind.pack.evidence)
    try:
        g = await ctx.model.generate_structured(BLIND_GUESS_PROMPT_ID, {"evidence_items": items}, BlindGuess, ctx)
    except Exception as exc:
        return BlindGuessResult(False, False, [], "llm", note=f"Blind guess failed ({type(exc).__name__}); not performed.")
    return evaluate_blind_guess(g.candidate_names, identity_terms, guesser="llm", confidence=g.confidence)


# ------------------------------------------------------------------ manifest block

def build_leakage_report(
    *, identity_findings: list[LeakFinding], temporal: TemporalAssessment,
    guess: BlindGuessResult | None, method: str,
) -> dict:
    """JSON-serializable block for R5's evals/cases/<id> manifest, field `leakage`."""
    direct = [f for f in identity_findings if f.kind != "possible_code"]
    indirect = [f for f in identity_findings if f.kind == "possible_code"]
    identified = bool(guess and guess.performed and guess.identified)
    if direct or identified or temporal.control_level == "uncontrolled":
        overall = "uncontrolled"
    elif (not indirect and temporal.control_level == "controlled" and guess and guess.performed):
        overall = "controlled_as_tested"
    else:
        overall = "partial"
    return {
        "overall": overall,
        "method": method,
        "identity_check": {
            "direct_leaks": [f.__dict__ for f in direct],
            "possible_indirect_identifiers": [f.__dict__ for f in indirect],
        },
        "temporal": {"control_level": temporal.control_level, "flags": temporal.flags},
        "blind_guess": None if guess is None else {
            "performed": guess.performed, "identified": guess.identified, "guesser": guess.guesser,
            "matched_terms": guess.matched_terms, "confidence": guess.confidence, "note": guess.note},
        "limitations": STANDING_LIMITATIONS,
    }