from fastapi import APIRouter

from app.api.v1.routes import analyses, case, scenes, system

router = APIRouter(prefix="/v1")
router.include_router(system.router)
router.include_router(case.router)
router.include_router(scenes.router)
router.include_router(analyses.router)
