from datetime import UTC, datetime

from fastapi import APIRouter

from app.api.dependencies import SettingsDep
from app.core.capabilities import CAPABILITY_STATUS
from app.schemas.system import CapabilityState, HealthResponse, MetaResponse

API_VERSION = "v1"

router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthResponse)
async def read_health(settings: SettingsDep) -> HealthResponse:
    return HealthResponse(
        status="ok",
        service=settings.app_name,
        version=settings.version,
        environment=settings.environment,
        timestamp=datetime.now(UTC),
    )


@router.get("/meta", response_model=MetaResponse)
async def read_meta(settings: SettingsDep) -> MetaResponse:
    return MetaResponse(
        service=settings.app_name,
        version=settings.version,
        api_version=API_VERSION,
        environment=settings.environment,
        capabilities=[
            CapabilityState(key=key, status=status) for key, status in CAPABILITY_STATUS.items()
        ],
    )
