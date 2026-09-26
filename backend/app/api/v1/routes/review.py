import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Query, Request
from fastapi.responses import Response

from app.api.dependencies import AnalysisDep
from app.review.export import to_csv, to_geojson
from app.review.labels import ReviewLabel, ReviewSource
from app.review.service import ReviewFilters, ReviewService
from app.schemas.review import REVIEWER_MAX, ReviewCreate

router = APIRouter(tags=["reviews"])


def get_review_service(request: Request) -> ReviewService:
    return request.app.state.review


ReviewDep = Annotated[ReviewService, Depends(get_review_service)]


def review_filters(
    source: ReviewSource | None = None,
    analysis_id: Annotated[str | None, Query(max_length=16)] = None,
    aoi_id: Annotated[str | None, Query(max_length=80)] = None,
    scene_id: Annotated[str | None, Query(max_length=120)] = None,
    label: ReviewLabel | None = None,
    reviewer: Annotated[str | None, Query(max_length=REVIEWER_MAX)] = None,
    history: bool = False,
) -> ReviewFilters:
    return ReviewFilters(source, analysis_id, aoi_id, scene_id, label, reviewer, history)


FiltersDep = Annotated[ReviewFilters, Depends(review_filters)]


@router.post("/analyses/{analysis_id}/zones/{zone_id}/review", status_code=201)
def create_review(
    analysis_id: str,
    zone_id: Annotated[str, Path(max_length=40)],
    payload: ReviewCreate,
    analysis: AnalysisDep,
    reviews: ReviewDep,
) -> dict[str, Any]:
    return reviews.add(analysis.get(analysis_id), zone_id, payload.model_dump(mode="json"))


@router.get("/analyses/{analysis_id}/reviews")
def read_analysis_reviews(
    analysis_id: str, analysis: AnalysisDep, reviews: ReviewDep
) -> dict[str, Any]:
    return reviews.for_analysis(analysis.get(analysis_id))


@router.get("/reviews")
def list_reviews(reviews: ReviewDep, filters: FiltersDep) -> dict[str, Any]:
    return {"items": reviews.records(filters), "summary": reviews.summary(filters)}


def _attachment(name: str) -> dict[str, str]:
    return {"Content-Disposition": f'attachment; filename="{name}"'}


@router.get("/reviews/export.geojson")
def export_reviews_geojson(reviews: ReviewDep, filters: FiltersDep) -> Response:
    body = json.dumps(to_geojson(reviews.records(filters)), ensure_ascii=False, indent=1)
    return Response(
        body,
        media_type="application/geo+json",
        headers=_attachment("littora-reviews.geojson"),
    )


@router.get("/reviews/export.csv")
def export_reviews_csv(reviews: ReviewDep, filters: FiltersDep) -> Response:
    return Response(
        "﻿" + to_csv(reviews.records(filters)),
        media_type="text/csv; charset=utf-8",
        headers=_attachment("littora-reviews.csv"),
    )
