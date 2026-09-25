from enum import StrEnum


class CapabilityKey(StrEnum):
    SCENE_CATALOG = "scene_catalog"
    FIELD_OBSERVATIONS = "field_observations"
    PAIR_REGISTRY = "pair_registry"
    QUALITY_MASKS = "quality_masks"
    ANALYSIS_REQUESTS = "analysis_requests"
    EXPORT = "export"
    DEBRIS_DETECTION = "debris_detection"
    SEGMENTATION = "segmentation"
    COVERAGE_ESTIMATION = "coverage_estimation"
    SPECTRAL_COMPOSITES = "spectral_composites"
    CONCENTRATION_MODEL = "concentration_model"
    CHANGE_TRACKING = "change_tracking"
    DRIFT_FORECAST = "drift_forecast"
    SURVEY_PLANNING = "survey_planning"
    MODEL_EVALUATION = "model_evaluation"


class CapabilityStatus(StrEnum):
    AVAILABLE = "available"
    PLANNED = "planned"


SERVICE_CAPABILITIES = frozenset(
    {
        CapabilityKey.SCENE_CATALOG,
        CapabilityKey.FIELD_OBSERVATIONS,
        CapabilityKey.PAIR_REGISTRY,
        CapabilityKey.QUALITY_MASKS,
        CapabilityKey.ANALYSIS_REQUESTS,
        CapabilityKey.EXPORT,
    }
)


def capability_status(
    detector_ready: bool = False, concentration_ready: bool = False
) -> dict[CapabilityKey, CapabilityStatus]:
    available = set(SERVICE_CAPABILITIES)
    if detector_ready:
        available |= {CapabilityKey.DEBRIS_DETECTION, CapabilityKey.SEGMENTATION}
    if concentration_ready:
        available.add(CapabilityKey.CONCENTRATION_MODEL)
    return {
        key: CapabilityStatus.AVAILABLE if key in available else CapabilityStatus.PLANNED
        for key in CapabilityKey
    }


CAPABILITY_STATUS = capability_status()
