from typing import Any

from fastapi import APIRouter
from starlette.concurrency import run_in_threadpool

from app.api.dependencies import AnalysisDep, SurveyDep
from app.schemas.survey import SurveyCreate

router = APIRouter(tags=["survey"])


@router.post("/analyses/{analysis_id}/survey")
async def create_survey(
    analysis_id: str,
    analysis: AnalysisDep,
    survey: SurveyDep,
    payload: SurveyCreate | None = None,
) -> dict[str, Any]:
    options = (payload or SurveyCreate()).options()
    return await run_in_threadpool(survey.run, analysis, analysis_id, options)


@router.get("/analyses/{analysis_id}/survey")
def read_survey(analysis_id: str, analysis: AnalysisDep, survey: SurveyDep) -> dict[str, Any]:
    return survey.cached(analysis, analysis_id)
