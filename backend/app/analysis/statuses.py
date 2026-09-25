from enum import StrEnum


class ResultStatus(StrEnum):
    DETECTED = "detected"
    NOT_DETECTED = "not_detected"
    INSUFFICIENT_DATA = "insufficient_data"
    RESEARCH_ESTIMATE = "research_estimate"
    CONCENTRATION_UNAVAILABLE = "concentration_unavailable"


STATUS_LABELS: dict[ResultStatus, str] = {
    ResultStatus.DETECTED: "обнаружено",
    ResultStatus.NOT_DETECTED: "не обнаружено",
    ResultStatus.INSUFFICIENT_DATA: "недостаточно данных",
    ResultStatus.RESEARCH_ESTIMATE: "исследовательская оценка",
    ResultStatus.CONCENTRATION_UNAVAILABLE: "концентрация недоступна",
}


class ValueKind(StrEnum):
    MEASUREMENT = "measurement"
    MODEL_ESTIMATE = "model_estimate"
    REQUEST_AREA = "request_area"
