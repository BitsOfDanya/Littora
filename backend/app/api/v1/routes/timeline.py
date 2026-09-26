import datetime as dt
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request
from shapely.geometry import box
from starlette.concurrency import run_in_threadpool

from app.analysis.service import AnalysisService
from app.api.dependencies import AnalysisDep
from app.api.v1.params import parse_bbox
from app.api.v1.routes.scenes import best_per_pass, scene_listing
from app.core.errors import AppError
from app.schemas.timeline import TimelineRunCreate
from app.timeline.service import MAX_RANGE_DAYS, Pass, TimelineQuery, TimelineService

router = APIRouter(tags=["timeline"])

SENTINEL2 = {"S2A", "S2B", "S2C"}


def get_timeline(request: Request) -> TimelineService:
    return request.app.state.timeline


TimelineDep = Annotated[TimelineService, Depends(get_timeline)]


def _query(
    bbox: tuple[float, float, float, float],
    date_from: dt.date,
    date_to: dt.date,
    aoi_id: str | None,
    aoi_name: str | None,
    target: str | None,
) -> TimelineQuery:
    if date_to < date_from:
        raise AppError("date_to раньше date_from")
    if (date_to - date_from).days > MAX_RANGE_DAYS:
        raise AppError(f"Период не длиннее {MAX_RANGE_DAYS} суток")
    return TimelineQuery(bbox, date_from, date_to, aoi_id, aoi_name, target)


def _passes(analysis: AnalysisService, query: TimelineQuery) -> list[Pass]:
    region = box(*query.bbox)
    start = dt.datetime.combine(query.date_from, dt.time.min, tzinfo=dt.UTC)
    end = dt.datetime.combine(query.date_to, dt.time(23, 59, 59), tzinfo=dt.UTC)
    scenes = [s for s in analysis.search_scenes(region, start, end) if s.platform in SENTINEL2]
    return [
        Pass(scene, scene_listing(scene, query.aoi_id, region))
        for scene in best_per_pass(scenes, region)
    ]


@router.get("/timeline")
def read_timeline(
    analysis: AnalysisDep,
    timeline: TimelineDep,
    bbox: Annotated[str, Query(max_length=120)],
    date_from: dt.date,
    date_to: dt.date,
    aoi_id: Annotated[str | None, Query(max_length=80)] = None,
    target: Annotated[str | None, Query(max_length=60)] = None,
) -> dict[str, Any]:
    area = parse_bbox(bbox)
    if area is None:
        raise AppError("Нужен bbox района")
    query = _query(area, date_from, date_to, aoi_id, None, target)
    return timeline.series(analysis, query, _passes(analysis, query))


@router.get("/timeline/compare")
def compare_passes(
    analysis: AnalysisDep,
    timeline: TimelineDep,
    before: Annotated[str, Query(max_length=16)],
    after: Annotated[str, Query(max_length=16)],
) -> dict[str, Any]:
    return timeline.compare(analysis, before, after)


@router.post("/timeline/runs")
async def create_run(
    payload: TimelineRunCreate, analysis: AnalysisDep, timeline: TimelineDep
) -> dict[str, Any]:
    query = _query(
        payload.bbox,
        payload.date_from,
        payload.date_to,
        payload.aoi_id,
        payload.aoi_name,
        payload.target,
    )

    def start() -> dict[str, Any]:
        timeline.validate(analysis, query)
        passes = _passes(analysis, query)
        return timeline.start(analysis, query, passes, payload.scene_ids, payload.max_passes)

    return await run_in_threadpool(start)


@router.get("/timeline/runs/{run_id}")
def read_run(run_id: str, timeline: TimelineDep) -> dict[str, Any]:
    return timeline.job(run_id)
