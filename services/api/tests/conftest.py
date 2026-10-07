import pytest
from fastapi.testclient import TestClient

from src.vic.config import get_settings
from src.vic.main import create_app
from src.vic.storage import get_repository


def new_client() -> TestClient:
    get_settings.cache_clear()
    get_repository.cache_clear()
    return TestClient(create_app())


@pytest.fixture()
def client():
    with new_client() as c:
        yield c
    get_settings.cache_clear()
    get_repository.cache_clear()