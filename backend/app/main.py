import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from app.analysis.service import AnalysisService
from app.api.router import API_PREFIX, api_router
from app.case.config import load_case_config
from app.case.repository import CaseRepository
from app.core.config import Settings, get_settings
from app.core.errors import register_error_handlers
from app.core.logging import configure_logging
from app.core.middleware import request_context_middleware
from app.core.request_context import REQUEST_ID_HEADER
from app.earth.catalog import StacCatalog

logger = logging.getLogger("littora")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        logger.info("%s %s started (%s)", settings.app_name, settings.version, settings.environment)
        yield

    app = FastAPI(
        title=settings.app_name,
        version=settings.version,
        docs_url=f"{API_PREFIX}/docs",
        redoc_url=None,
        openapi_url=f"{API_PREFIX}/openapi.json",
        lifespan=lifespan,
    )
    app.state.settings = settings
    repository = CaseRepository(settings)
    catalog_url = load_case_config(settings.case_config).pairing.catalog
    app.state.repository = repository
    app.state.analysis = AnalysisService(repository, StacCatalog(catalog_url), settings.storage_dir)

    app.middleware("http")(request_context_middleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=[REQUEST_ID_HEADER],
    )
    register_error_handlers(app)
    app.include_router(api_router)

    @app.get("/", include_in_schema=False)
    async def redirect_to_docs() -> RedirectResponse:
        return RedirectResponse(url=f"{API_PREFIX}/docs")

    return app


app = create_app()
