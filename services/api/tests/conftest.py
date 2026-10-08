import pytest
from fastapi.testclient import TestClient

from vic.config import get_settings
from vic.main import create_app
from vic.storage import get_repository


def new_client() -> TestClient:
    get_settings.cache_clear()
    get_repository.cache_clear()
    return TestClient(create_app())


@pytest.fixture(autouse=True)
def _isolated_env(tmp_path, monkeypatch):
    """Every test gets its own database and a clean environment (a developer .env must not leak in)."""
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{(tmp_path / 'vic.sqlite3').as_posix()}")
    monkeypatch.setenv("RUN_BACKEND", "mock")
    monkeypatch.setenv("API_SHARED_SECRET", "")
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("DEV_STUBS", "false")
    get_settings.cache_clear()
    get_repository.cache_clear()
    yield
    get_settings.cache_clear()
    get_repository.cache_clear()


@pytest.fixture()
def client():
    with new_client() as c:
        yield c