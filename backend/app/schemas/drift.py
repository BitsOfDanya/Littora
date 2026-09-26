from pydantic import BaseModel, Field

MAX_HOURS = 72
MAX_HINDCAST_HOURS = 48


class DriftCreate(BaseModel):
    hours: int = Field(default=MAX_HOURS, ge=1, le=MAX_HOURS)
    hindcast_hours: int = Field(default=MAX_HINDCAST_HOURS, ge=0, le=MAX_HINDCAST_HOURS)


class DriftSkill(BaseModel):
    value: float
    ci: list[float] | None
    verdict: str | None


class DriftErrorHorizon(BaseModel):
    horizon_h: int
    windows: int
    drifters: int
    groups: int
    service_km: float
    service_ci_km: list[float] | None
    stationary_km: float
    persistence_km: float
    skill_vs_stationary: DriftSkill | None


class DriftErrorSet(BaseModel):
    key: str
    label: str
    horizons: list[DriftErrorHorizon]


class DriftCoverageHorizon(BaseModel):
    horizon_h: int
    windows: int
    before: float
    after: float
    after_ci: list[float] | None


class DriftCoverageSet(BaseModel):
    key: str
    label: str
    windows: int
    drifters: int
    groups: int
    horizons: list[DriftCoverageHorizon]


class DriftCalibration(BaseModel):
    variant: str
    noise_ms: float
    decorrelation_h: float
    effective_diffusivity_m2s: float | None
    nominal: float
    sets: list[DriftCoverageSet]


class DriftValidation(BaseModel):
    errors: list[DriftErrorSet]
    calibration: DriftCalibration | None
    sources: list[str]
