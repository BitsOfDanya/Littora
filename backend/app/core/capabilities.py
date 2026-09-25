from enum import StrEnum


class CapabilityKey(StrEnum):
    SCENE_CATALOG = "scene_catalog"
    DEBRIS_DETECTION = "debris_detection"
    SEGMENTATION = "segmentation"
    COVERAGE_ESTIMATION = "coverage_estimation"
    CHANGE_TRACKING = "change_tracking"
    DRIFT_FORECAST = "drift_forecast"
    SURVEY_PLANNING = "survey_planning"
    MODEL_EVALUATION = "model_evaluation"


class CapabilityStatus(StrEnum):
    AVAILABLE = "available"
    PLANNED = "planned"


CAPABILITY_STATUS: dict[CapabilityKey, CapabilityStatus] = {
    key: CapabilityStatus.PLANNED for key in CapabilityKey
}
