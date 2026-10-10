import pytest
from fastapi.testclient import TestClient

from vic.config import get_settings
from vic.main import create_app
from vic.runner import get_manager
from vic.storage import get_repository


def _clear() -> None:
    get_settings.cache_clear()
    get_repository.cache_clear()
    get_manager.cache_clear()


def new_client() -> TestClient:
    _clear()
    return TestClient(create_app())


@pytest.fixture(autouse=True)
def _isolated_env(tmp_path, monkeypatch):
    """Every test gets its own database and a clean environment (a developer .env must not leak in)."""
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{(tmp_path / 'vic.sqlite3').as_posix()}")
    # Legacy bounded-mode regressions opt in; diagnostic-mode tests override explicitly.
    monkeypatch.setenv("PROVIDER_INPUT_LIMIT_TEST", "false")
    monkeypatch.setenv("CONTINUE_ON_NODE_VALIDATION_ERROR", "false")
    monkeypatch.setenv("RUN_BACKEND", "mock")
    monkeypatch.setenv("API_SHARED_SECRET", "")
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("DEV_STUBS", "false")
    monkeypatch.setenv("STUB_DELAY_SECONDS", "0")
    _clear()
    yield
    _clear()


@pytest.fixture()
def client():
    with new_client() as c:
        yield c