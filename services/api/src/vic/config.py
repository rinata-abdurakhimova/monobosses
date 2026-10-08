"""Runtime settings. Names from the contract (section 5) plus additive R2-02 settings."""
from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- contract env names
    llm_provider: str = "placeholder"
    llm_model: str = "placeholder-model"
    llm_api_key: str = ""
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
    llm_price_input_per_mtok: float | None = None    # USD per 1M input tokens
    llm_price_output_per_mtok: float | None = None   # USD per 1M output tokens
    llm_price_date: str | None = None                # date the prices were checked

    @field_validator("max_run_cost_usd", "llm_price_input_per_mtok", "llm_price_output_per_mtok",
                     "llm_price_date", mode="before")
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
            "llm_max_retries": self.llm_max_retries, "llm_max_repairs": self.llm_max_repairs,
            "llm_request_timeout_seconds": self.llm_request_timeout_seconds,
            "llm_max_output_tokens": self.llm_max_output_tokens,
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
