"""Single LLM adapter. STUB in R2-01; implemented in R2-02 (issue #7)."""
from typing import Any, TypeVar

from pydantic import BaseModel

from vic.run_context import RunContext

T = TypeVar("T", bound=BaseModel)

PROMPT_IDS = ("science", "translation", "clinical", "market", "investment", "chair", "audit", "ip_licensing")


async def generate_structured(prompt_id: str, payload: dict[str, Any], response_model: type[T],
                              ctx: RunContext) -> T:
    """Call the model, validate the answer with `response_model`, bounded retries, usage tracking."""
    raise NotImplementedError("LLM adapter is implemented in R2-02 (#7)")