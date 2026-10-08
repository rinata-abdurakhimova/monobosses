"""One paid, bounded connectivity check. Run from services/api: python scripts/check_llm.py.

Reads server settings/.env; never prints credentials, response text or raw errors.
Does not run the committee or write a case/report. No automatic retries.
"""
import asyncio

from pydantic import ValidationError

from vic.config import Settings
from vic.failures import RunFailure
from vic.llm import make_provider


async def check() -> int:
    try:
        settings = Settings()
        response = await make_provider(settings).complete(
            system="Reply with the single word OK.",
            messages=[{"role": "user", "content": "Connectivity check."}],
            model=settings.llm_model, max_tokens=256,
            timeout=min(settings.llm_request_timeout_seconds, 30),
        )
    except RunFailure as exc:
        print(f"FAIL {exc.code}: {exc.message}")
        return 1
    except (ValidationError, ValueError):
        print("FAIL: invalid provider configuration; check LLM_PROVIDER and LLM_BASE_URL")
        return 1
    except Exception:  # noqa: BLE001 -- CLI boundary must not expose SDK errors containing secrets.
        print("FAIL: provider setup failed; check installed dependencies and configuration")
        return 1
    print(f"OK: model response received; input_tokens={response.input_tokens}, "
          f"output_tokens={response.output_tokens}")
    print("Connectivity verified only; committee completion and analysis quality are not verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(check()))
