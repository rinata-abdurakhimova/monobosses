"""Runtime settings. Names from the contract (section 5) plus additive R2-02 settings."""
from functools import lru_cache
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- contract env names
    llm_provider: str = "placeholder"
    llm_model: str = "placeholder-model"
    llm_api_key: str = ""
    # OpenAI-compatible base URL from the provider's connection instructions.
    # No default: never send a mentor key to a guessed host.
    llm_base_url: str = ""
    database_url: str = "sqlite:///./data/vic.sqlite3"
    cors_origins: str = "http://localhost:3000"
    max_upload_bytes: int = 10 * 1024 * 1024
    max_run_cost_usd: float | None = Field(default=None, gt=0)
    max_run_seconds: int = Field(default=600, gt=0)

    # --- additive (R2-02)
    app_env: Literal["development", "production"] = "development"
    host: str = "127.0.0.1"
    port: int = 8000
    api_shared_secret: str = ""           # required in production
    max_concurrent_runs: int = Field(default=2, gt=0)
    run_backend: Literal["pipeline", "mock"] = "pipeline"
    dev_stubs: bool = False               # synthetic development mode (never in production)
    stub_modules: str = ""                # comma-separated function names to stub; empty = all
    stub_delay_seconds: float = 0.0       # simulates stage duration in dev_stubs mode
    seed_synthetic: bool = True           # seed case-synthetic-01 and fixture runs
    llm_max_retries: int = Field(default=2, ge=0)
    llm_max_repairs: int = Field(default=1, ge=0)
    llm_request_timeout_seconds: float = Field(default=120.0, gt=0)
    llm_max_output_tokens: int = Field(default=4096, gt=0)
    clinical_reasoning_effort: Literal["low", "medium", "high", "xhigh", "max"] | None = "low"
    market_reasoning_effort: Literal["low", "medium", "high", "xhigh", "max"] | None = "low"
    node_request_max_bytes: int = Field(default=15500, gt=0)
    # Diagnostic mode: let the gateway decide whether a node request fits.
    enforce_node_request_budget: bool = False
    node_initial_request_bytes: int = Field(default=13500, gt=0)
    science_request_target_bytes: int = Field(default=10000, gt=1000)
    node_reasoning_effort: Literal["low", "medium", "high", "xhigh", "max"] | None = "low"
    # Provisional application cap, NOT a measured mentor gateway limit.
    market_request_max_bytes: int = Field(default=18000, gt=0)
    llm_price_input_per_mtok: float | None = None    # USD per 1M input tokens
    llm_price_output_per_mtok: float | None = None   # USD per 1M output tokens
    llm_price_date: str | None = None                # date the prices were checked

    @field_validator("llm_base_url")
    @classmethod
    def _validate_api_url(cls, value: str) -> str:
        value = value.strip()
        if not value:
            return value
        parts = urlsplit(value)
        if (parts.scheme not in {"https", "http"} or not parts.hostname
                or parts.username is not None or parts.password is not None
                or parts.fragment or parts.query):
            raise ValueError("LLM_BASE_URL must be an HTTP(S) URL without credentials, query or fragment")
        if parts.scheme == "http" and parts.hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError("LLM_BASE_URL must use HTTPS outside localhost")
        return value.rstrip("/")

    @field_validator("max_run_cost_usd", "llm_price_input_per_mtok", "llm_price_output_per_mtok",
                     "llm_price_date", "clinical_reasoning_effort", "market_reasoning_effort", "node_reasoning_effort", mode="before")
    @classmethod
    def _empty_to_none(cls, value):
        return None if isinstance(value, str) and not value.strip() else value

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def stub_module_set(self) -> set[str]:
        return {n.strip() for n in self.stub_modules.split(",") if n.strip()}

    @property
    def sqlite_path(self) -> str:
        prefix = "sqlite:///"
        if not self.database_url.startswith(prefix):
            raise ValueError("DATABASE_URL must look like sqlite:///path/to/file.sqlite3 "
                             "(only SQLite is supported in this version)")
        return self.database_url[len(prefix):]

    def public_config(self) -> dict:
        """Non-secret configuration that goes into the trace and the config version."""
        return {
            "llm_provider": self.llm_provider, "llm_model": self.llm_model,
            "llm_base_url": self.llm_base_url,
            "llm_max_retries": self.llm_max_retries, "llm_max_repairs": self.llm_max_repairs,
            "llm_request_timeout_seconds": self.llm_request_timeout_seconds,
            "llm_max_output_tokens": self.llm_max_output_tokens,
            "clinical_reasoning_effort": self.clinical_reasoning_effort,
            "market_reasoning_effort": self.market_reasoning_effort,
            "node_request_max_bytes": self.node_request_max_bytes,
            "enforce_node_request_budget": self.enforce_node_request_budget,
            "node_initial_request_bytes": self.node_initial_request_bytes,
            "science_request_target_bytes": self.science_request_target_bytes,
            "node_reasoning_effort": self.node_reasoning_effort,
            "market_request_max_bytes": self.market_request_max_bytes,
            "llm_price_input_per_mtok": self.llm_price_input_per_mtok,
            "llm_price_output_per_mtok": self.llm_price_output_per_mtok,
            "llm_price_date": self.llm_price_date,
            "max_run_seconds": self.max_run_seconds, "max_run_cost_usd": self.max_run_cost_usd,
            "dev_stubs": self.dev_stubs,
            "stub_modules": self.stub_modules
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()
