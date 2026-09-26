from pydantic import BaseModel, Field

from app.survey.planner import MAX_TARGETS, SurveyOptions

DEFAULTS = SurveyOptions()


class SurveyCreate(BaseModel):
    speed_kn: float = Field(default=DEFAULTS.speed_kn, gt=0, le=40)
    uav_range_km: float = Field(default=DEFAULTS.uav_range_km, gt=0, le=100)
    route_targets: int = Field(default=DEFAULTS.route_targets, ge=1, le=MAX_TARGETS)
    dwell_min: int = Field(default=DEFAULTS.dwell_min, ge=0, le=240)
    lead_h: float = Field(default=DEFAULTS.lead_h, ge=0, le=48)

    def options(self) -> SurveyOptions:
        return SurveyOptions(**self.model_dump())
