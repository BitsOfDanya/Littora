from fastapi import APIRouter

from app.api.v1.router import router as v1_router

API_PREFIX = "/api"

api_router = APIRouter(prefix=API_PREFIX)
api_router.include_router(v1_router)
