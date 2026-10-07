"""Runtime settings. Env variable names follow the shared contract (section 5)."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    llm_provider: str = "placeholder"
    llm_model: str = "placeholder-model"
    llm_api_key: str = ""
    database_url: str = "sqlite:///./data/vic.sqlite3"
    cors_origins: str = "http://localhost:3000"
    max_upload_bytes: int = 10 * 1024 * 1024
    max_run_cost_usd: float | None = None
    max_run_seconds: int = 600
    api_shared_secret: str = ""  # used by server auth in R2-02

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()