import datetime as dt
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Query

from app.api.dependencies import RepositoryDep
from app.api.v1.params import parse_bbox
from app.case.data import CaseDataMissingError
from app.case.repository import ObservationFilter
from app.core.errors import NotFoundError

router = APIRouter(tags=["case"])

Decision = Literal["accepted", "rejected"]
PairDecisionFilter = Literal["accepted", "candidate", "not_evaluated", "rejected"]
EventDecisionFilter = Literal["accepted", "candidate", "not_evaluated", "rejected", "not_used"]


def _data_or_404(repository: RepositoryDep):
    try:
        return repository.data()
    except CaseDataMissingError as error:
        raise NotFoundError("Данные кейса не найдены: положите CSV в data/case/") from error


@router.get("/case/targets")
def read_targets(repository: RepositoryDep) -> dict[str, Any]:
    data = _data_or_404(repository)
    return {"primary": data.config.primary_target.key, "targets": repository.targets()}


@router.get("/case/summary")
def read_summary(repository: RepositoryDep) -> dict[str, Any]:
    data = _data_or_404(repository)
    registry = repository.registry()
    return {
        "primary": data.config.primary_target.key,
        "targets": repository.targets(),
        "records": len(data.records),
        "registry": registry["summary"],
    }


@router.get("/observations")
def read_observations(
    repository: RepositoryDep,
    target: Annotated[str | None, Query(max_length=60)] = None,
    decision: Decision | None = None,
    source: Annotated[str | None, Query(max_length=60)] = None,
    date_from: dt.date | None = None,
    date_to: dt.date | None = None,
    bbox: Annotated[str | None, Query(max_length=120)] = None,
) -> dict[str, Any]:
    _data_or_404(repository)
    filters = ObservationFilter(
        target=target,
        decision=decision,
        source=source,
        date_from=date_from,
        date_to=date_to,
        bbox=parse_bbox(bbox),
    )
    features = repository.observations(filters)
    return {"type": "FeatureCollection", "features": features}


@router.get("/pairs")
def read_pairs(
    repository: RepositoryDep,
    event_id: Annotated[str | None, Query(max_length=80)] = None,
    decision: PairDecisionFilter | None = None,
    target: Annotated[str | None, Query(max_length=60)] = None,
) -> dict[str, Any]:
    rows = repository.registry()["pairs"]
    items = [
        row
        for row in rows
        if (event_id is None or row["event_id"] == event_id)
        and (decision is None or row["decision"] == decision)
        and (target is None or target in row["target_keys"].split(";"))
    ]
    return {"total": len(items), "items": items}


@router.get("/events")
def read_events(
    repository: RepositoryDep,
    decision: EventDecisionFilter | None = None,
    target: Annotated[str | None, Query(max_length=60)] = None,
) -> dict[str, Any]:
    events = repository.registry()["events"]
    features = [
        feature
        for feature in events.get("features", [])
        if (decision is None or feature["properties"]["decision"] == decision)
        and (target is None or target in feature["properties"]["target_keys"])
    ]
    return {"type": "FeatureCollection", "features": features}
