import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from app.analysis.conditions import OpenMeteoWeather
from app.analysis.detector import OnnxDetector
from app.analysis.field_models import FieldConcentrationModel
from app.analysis.service import AnalysisService
from app.analysis.structures import OSM_DIR, OsmStructures
from app.api.router import API_PREFIX, api_router
from app.case.config import load_case_config
from app.case.repository import CaseRepository
from app.core.config import Settings, get_settings
from app.core.errors import register_error_handlers
from app.core.logging import configure_logging
from app.core.middleware import request_context_middleware
from app.core.request_context import REQUEST_ID_HEADER
from app.drift.forcing import OpenMeteoClient, OpenMeteoForcing
from app.drift.places import load_places
from app.drift.service import FORCING_DIR, DriftService
from app.earth.catalog import StacCatalog
from app.evaluation.reports import EvaluationReports
from app.review.audit import AUDIT_FILE
from app.review.service import REVIEWS_DIR, ReviewService
from app.survey.ports import load_ports
from app.survey.service import SurveyService
from app.timeline.service import TimelineService

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
    concentration = FieldConcentrationModel.load(settings.models_dir / "concentration" / "service")
    detector = OnnxDetector.load(settings.models_dir / "detector" / "service")
    app.state.analysis = AnalysisService(
        repository,
        StacCatalog(catalog_url),
        settings.storage_dir,
        detector=detector,
        concentration_model=concentration,
        weather=OpenMeteoWeather(OpenMeteoClient(settings.storage_dir / FORCING_DIR)),
        structures=OsmStructures(settings.storage_dir / OSM_DIR),
        ports=load_ports(settings.data_dir / "aoi" / "ports.geojson"),
    )
    app.state.evaluation = EvaluationReports(settings.reports_dir, settings.models_dir)
    app.state.timeline = TimelineService()
    app.state.drift = DriftService(
        OpenMeteoForcing(settings.storage_dir / FORCING_DIR),
        places=load_places(settings.data_dir / "aoi" / "russia.geojson"),
    )
    app.state.survey = SurveyService(load_ports(settings.data_dir / "aoi" / "ports.geojson"))
    app.state.review = ReviewService(
        settings.storage_dir / REVIEWS_DIR, settings.data_dir / AUDIT_FILE
    )

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
