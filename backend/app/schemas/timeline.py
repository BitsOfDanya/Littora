import datetime as dt
from typing import Annotated

from pydantic import BaseModel, Field

from app.timeline.service import DEFAULT_PASSES, MAX_PASSES

SceneId = Annotated[str, Field(max_length=120, pattern=r"^[A-Za-z0-9_.-]+$")]


class TimelineRunCreate(BaseModel):
    bbox: tuple[float, float, float, float]
    date_from: dt.date
    date_to: dt.date
    aoi_id: str | None = Field(default=None, max_length=80)
    aoi_name: str | None = Field(default=None, max_length=160)
    target: str | None = Field(default=None, max_length=60)
    max_passes: int = Field(default=DEFAULT_PASSES, ge=1, le=MAX_PASSES)
    scene_ids: list[SceneId] | None = Field(default=None, max_length=MAX_PASSES)
