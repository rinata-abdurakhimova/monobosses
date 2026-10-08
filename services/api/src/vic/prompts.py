"""Prompt lookup. Prompts live next to the owner modules; the version is a content hash."""
import hashlib
from dataclasses import dataclass
from pathlib import Path

from vic.failures import PromptNotFound

_ROOT = Path(__file__).resolve().parent
SEARCH_DIRS = [
    _ROOT / "agents" / "science" / "prompts",
    _ROOT / "agents" / "business" / "prompts",
    _ROOT / "evidence" / "prompts",
]
# prompt_id -> candidate file stems (edit after checking the real file names)
ALIASES: dict[str, list[str]] = {
    "science": ["science", "scientific"],
    "translation": ["translation"],
    "clinical": ["clinical"],
    "market": ["market"],
    "investment": ["investment"],
    "chair": ["chair", "committee"],
    "audit": ["audit", "auditor"],
}


@dataclass(frozen=True)
class LoadedPrompt:
    prompt_id: str
    text: str
    version: str
    path: Path | None


def load_prompt(prompt_id: str) -> LoadedPrompt:
    for directory in SEARCH_DIRS:
        for stem in ALIASES.get(prompt_id, [prompt_id]):
            path = directory / f"{stem}.md"
            if path.is_file():
                text = path.read_text(encoding="utf-8")
                version = hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]
                return LoadedPrompt(prompt_id, text, version, path)
    raise PromptNotFound(f"No prompt file found for prompt id '{prompt_id}'")


def available_prompts() -> dict[str, str | None]:
    """prompt_id -> version, or None when the file is missing (used by scripts/check_wiring)."""
    out: dict[str, str | None] = {}
    for prompt_id in ALIASES:
        try:
            out[prompt_id] = load_prompt(prompt_id).version
        except PromptNotFound:
            out[prompt_id] = None
    return out