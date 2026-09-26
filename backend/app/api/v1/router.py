from fastapi import APIRouter

from app.api.v1.routes import (
    analyses,
    case,
    drift,
    models,
    review,
    scenes,
    survey,
    system,
    timeline,
)

router = APIRouter(prefix="/v1")
router.include_router(system.router)
router.include_router(case.router)
router.include_router(scenes.router)
router.include_router(analyses.router)
router.include_router(drift.router)
router.include_router(survey.router)
router.include_router(models.router)
router.include_router(timeline.router)
router.include_router(review.router)
