from typing import Any

from fastapi import APIRouter
from starlette.concurrency import run_in_threadpool

from app.api.dependencies import AnalysisDep, DriftDep
from app.schemas.drift import DriftCreate

router = APIRouter(tags=["drift"])


@router.post("/analyses/{analysis_id}/drift")
async def create_drift(
    analysis_id: str,
    analysis: AnalysisDep,
    drift: DriftDep,
    payload: DriftCreate | None = None,
) -> dict[str, Any]:
    options = payload or DriftCreate()
    return await run_in_threadpool(
        drift.run, analysis, analysis_id, options.hours, options.hindcast_hours
    )


@router.get("/analyses/{analysis_id}/drift")
def read_drift(analysis_id: str, analysis: AnalysisDep, drift: DriftDep) -> dict[str, Any]:
    return drift.cached(analysis, analysis_id)
