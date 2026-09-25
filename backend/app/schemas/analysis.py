import datetime as dt

from pydantic import BaseModel, Field


class AnalysisCreate(BaseModel):
    bbox: tuple[float, float, float, float]
    date: dt.date
    window_days: int = Field(default=3, ge=0, le=15)
    aoi_id: str | None = Field(default=None, max_length=80)
    aoi_name: str | None = Field(default=None, max_length=160)
    scene_id: str | None = Field(default=None, max_length=120, pattern=r"^[A-Za-z0-9_.-]+$")
    target: str | None = Field(default=None, max_length=60)
