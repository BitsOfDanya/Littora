from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from app import __version__

Environment = Literal["local", "development", "staging", "production"]

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPOSITORY_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="LITTORA_",
        env_file=(REPOSITORY_DIR / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Littora API"
    version: str = __version__
    environment: Environment = "local"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://127.0.0.1:3000"]
    )
    data_dir: Path = REPOSITORY_DIR / "data"
    reports_dir: Path = REPOSITORY_DIR / "reports"
    storage_dir: Path = REPOSITORY_DIR / "data" / "processed" / "analyses"
    case_config: Path = BACKEND_DIR / "config" / "case.toml"

    @field_validator("cors_origins", mode="before")
    @classmethod
    def split_cors_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def registry_dir(self) -> Path:
        return self.reports_dir / "registry"


@lru_cache
def get_settings() -> Settings:
    return Settings()
