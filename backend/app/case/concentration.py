from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.case.config import ConcentrationRules
from app.case.records import CaseRecord

UNIT = "шт./км²"


class CheckStatus(StrEnum):
    MATCH = "match"
    ROUNDING = "rounding"
    MISMATCH = "mismatch"
    PUBLISHED_ONLY = "published_only"
    MISSING = "missing"


CHECK_LABELS: dict[CheckStatus, str] = {
    CheckStatus.MATCH: "N/A совпадает с опубликованным значением",
    CheckStatus.ROUNDING: "N/A совпадает с точностью до округления источника",
    CheckStatus.MISMATCH: "N/A расходится с опубликованным значением",
    CheckStatus.PUBLISHED_ONLY: "только опубликованная оценка: нет N или A",
    CheckStatus.MISSING: "нет опубликованной концентрации",
}


def density(items: float, area_km2: float) -> float:
    if items < 0:
        raise ValueError("number of items must not be negative")
    if area_km2 <= 0:
        raise ValueError("surveyed area must be positive")
    return items / area_km2


def strip_area_km2(length_km: float, width_m: float) -> float:
    if length_km < 0 or width_m < 0:
        raise ValueError("strip size must not be negative")
    return length_km * width_m / 1000.0


def absolute_error(estimate: float, reference: float) -> float:
    return abs(estimate - reference)


@dataclass(frozen=True)
class ConcentrationCheck:
    published: float | None
    recomputed: float | None
    absolute_difference: float | None
    relative_difference: float | None
    status: CheckStatus

    @property
    def label(self) -> str:
        return CHECK_LABELS[self.status]


def check_record(record: CaseRecord, rules: ConcentrationRules) -> ConcentrationCheck:
    published = record.published_concentration
    items, area = record.items, record.area_km2
    recomputed = density(items, area) if items is not None and area and area > 0 else None
    if published is None and recomputed is None:
        return ConcentrationCheck(None, None, None, None, CheckStatus.MISSING)
    if recomputed is None:
        return ConcentrationCheck(published, None, None, None, CheckStatus.PUBLISHED_ONLY)
    if published is None:
        return ConcentrationCheck(None, recomputed, None, None, CheckStatus.MISSING)
    difference = absolute_error(recomputed, published)
    relative = difference / published if published else (0.0 if difference == 0 else None)
    if relative is not None and relative <= rules.match_relative:
        status = CheckStatus.MATCH
    elif relative is not None and relative <= rules.rounding_relative:
        status = CheckStatus.ROUNDING
    else:
        status = CheckStatus.MISMATCH
    return ConcentrationCheck(published, recomputed, difference, relative, status)
