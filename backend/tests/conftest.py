from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app

TEST_ORIGIN = "http://localhost:3000"


@pytest.fixture
def settings() -> Settings:
    return Settings(_env_file=None, environment="local", cors_origins=[TEST_ORIGIN])


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as test_client:
        yield test_client
