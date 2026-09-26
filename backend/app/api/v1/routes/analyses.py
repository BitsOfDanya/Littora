import datetime as dt
import json
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Query, Request
from fastapi.responses import FileResponse, Response
from starlette.concurrency import run_in_threadpool

from app.analysis.export import to_csv, to_geojson
from app.analysis.service import (
    EXTRA_LAYER_FILES,
    IMAGE_FILE,
    MASK_FILE,
    PROBABILITY_FILE,
    AnalysisRequest,
)
from app.analysis.upload import MAX_BYTES, UploadError
from app.api.dependencies import AnalysisDep
from app.api.v1.params import parse_bbox
from app.core.errors import NotFoundError
from app.schemas.analysis import AnalysisCreate

router = APIRouter(tags=["analyses"])

StatusFilter = Literal[
    "detected",
    "not_detected",
    "insufficient_data",
    "research_estimate",
    "concentration_unavailable",
]


@router.post("/analyses")
async def create_analysis(
    payload: AnalysisCreate, analysis: AnalysisDep, response: Response
) -> dict[str, Any]:
    request = AnalysisRequest(**payload.model_dump())
    result = await run_in_threadpool(analysis.submit, request)
    if result.get("state") == "running":
        response.status_code = 202
    return result


@router.get("/analyses")
def list_analyses(
    analysis: AnalysisDep,
    status: StatusFilter | None = None,
    aoi_id: Annotated[str | None, Query(max_length=80)] = None,
    date_from: dt.date | None = None,
    date_to: dt.date | None = None,
) -> dict[str, Any]:
    items = analysis.history(status, aoi_id=aoi_id, date_from=date_from, date_to=date_to)
    return {"items": items}


@router.get("/analyses/{analysis_id}")
def read_analysis(analysis_id: str, analysis: AnalysisDep) -> dict[str, Any]:
    return analysis.get(analysis_id)


@router.get("/analyses/{analysis_id}/conditions")
async def read_conditions(analysis_id: str, analysis: AnalysisDep) -> dict[str, Any]:
    return await run_in_threadpool(analysis.conditions, analysis_id)


@router.get("/analyses/{analysis_id}/image.png", response_class=FileResponse)
def read_image(analysis_id: str, analysis: AnalysisDep) -> FileResponse:
    return FileResponse(analysis.layer_path(analysis_id, IMAGE_FILE), media_type="image/png")


@router.get("/analyses/{analysis_id}/probability.png", response_class=FileResponse)
def read_probability(analysis_id: str, analysis: AnalysisDep) -> FileResponse:
    return FileResponse(analysis.layer_path(analysis_id, PROBABILITY_FILE), media_type="image/png")


@router.get("/analyses/{analysis_id}/mask.png", response_class=FileResponse)
def read_mask(analysis_id: str, analysis: AnalysisDep) -> FileResponse:
    return FileResponse(analysis.layer_path(analysis_id, MASK_FILE), media_type="image/png")


def _attachment(name: str) -> dict[str, str]:
    return {"Content-Disposition": f'attachment; filename="{name}"'}


@router.post("/uploads", status_code=201)
async def upload_image(
    request: Request,
    analysis: AnalysisDep,
    name: Annotated[str, Query(max_length=120)] = "снимок",
    bbox: Annotated[str | None, Query(max_length=120)] = None,
    date: dt.date | None = None,
) -> dict[str, Any]:
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > MAX_BYTES:
        raise UploadError("Файл больше 150 МБ")
    content = await request.body()
    return await run_in_threadpool(analysis.analyze_upload, content, name, parse_bbox(bbox), date)


@router.get("/concentration/domains")
def read_concentration_domains(analysis: AnalysisDep) -> dict[str, Any]:
    return analysis.concentration_domains()


@router.get("/analyses/{analysis_id}/targets")
def read_target_estimates(analysis_id: str, analysis: AnalysisDep) -> dict[str, Any]:
    return analysis.target_estimates(analysis_id)


@router.get("/analyses/{analysis_id}/pixel")
async def read_pixel_values(
    analysis_id: str,
    analysis: AnalysisDep,
    lon: Annotated[float, Query(ge=-180, le=180)],
    lat: Annotated[float, Query(ge=-90, le=90)],
) -> dict[str, Any]:
    return await run_in_threadpool(analysis.pixel, analysis_id, lon, lat)


@router.get("/analyses/{analysis_id}/layers/{name}", response_class=FileResponse)
def read_extra_layer(analysis_id: str, name: str, analysis: AnalysisDep) -> FileResponse:
    if name not in EXTRA_LAYER_FILES:
        raise NotFoundError("Такого слоя нет")
    return FileResponse(analysis.layer_path(analysis_id, name), media_type="image/png")


@router.get("/analyses/{analysis_id}/export.geojson")
def export_geojson(analysis_id: str, analysis: AnalysisDep) -> Response:
    result = analysis.get(analysis_id)
    body = json.dumps(to_geojson(result), ensure_ascii=False, indent=1)
    return Response(
        body,
        media_type="application/geo+json",
        headers=_attachment(f"littora-{analysis_id}.geojson"),
    )


@router.get("/analyses/{analysis_id}/export.csv")
def export_csv(analysis_id: str, analysis: AnalysisDep) -> Response:
    result = analysis.get(analysis_id)
    body = "﻿" + to_csv(result)
    return Response(
        body,
        media_type="text/csv; charset=utf-8",
        headers=_attachment(f"littora-{analysis_id}.csv"),
    )
