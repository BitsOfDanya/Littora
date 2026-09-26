from datetime import UTC, datetime

from fastapi import APIRouter

from app.api.dependencies import (
    AnalysisDep,
    EvaluationDep,
    OptionalDriftDep,
    OptionalSurveyDep,
    SettingsDep,
)
from app.core.capabilities import capability_status
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
def read_meta(
    settings: SettingsDep,
    analysis: AnalysisDep,
    drift: OptionalDriftDep,
    evaluation: EvaluationDep,
    survey: OptionalSurveyDep,
) -> MetaResponse:
    statuses = capability_status(
        detector_ready=analysis.detector.name is not None,
        concentration_ready=analysis.concentration_model.name is not None,
        drift_ready=drift is not None,
        evaluation_ready=evaluation.available(),
        survey_ready=survey is not None,
    )
    return MetaResponse(
        service=settings.app_name,
        version=settings.version,
        api_version=API_VERSION,
        environment=settings.environment,
        capabilities=[CapabilityState(key=key, status=status) for key, status in statuses.items()],
    )
