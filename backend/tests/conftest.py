import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app

TEST_ORIGIN = "http://localhost:3000"
MISSING_MODELS = "/nonexistent-littora-models"

os.environ.setdefault("LITTORA_MODELS_DIR", MISSING_MODELS)


@pytest.fixture
def settings() -> Settings:
    return Settings(
        _env_file=None,
        environment="local",
        cors_origins=[TEST_ORIGIN],
        models_dir=Path(MISSING_MODELS),
    )


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as test_client:
        yield test_client
