from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.case.concentration import CheckStatus, ConcentrationCheck, check_record
from app.case.config import CaseConfig
from app.case.records import CaseRecord


class SelectionReason(StrEnum):
    ACCEPTED = "accepted"
    ITEM_OBSERVATION = "item_observation"
    CATEGORY = "category"
    PROFILE_NOT_TARGETED = "profile_not_targeted"
    SCOPE_MISMATCH = "scope_mismatch"
    NO_CONCENTRATION = "no_concentration"
    CONCENTRATION_MISMATCH = "concentration_mismatch"
    EXCLUDED_FLAG = "excluded_flag"


REASON_LABELS: dict[SelectionReason, str] = {
    SelectionReason.ACCEPTED: "принята",
    SelectionReason.ITEM_OBSERVATION: (
        "объектная запись: своей плотности нет, числитель трансекты по ней не восстановить"
    ),
    SelectionReason.CATEGORY: "отдельная категория, а не суммарная величина",
    SelectionReason.PROFILE_NOT_TARGETED: "профиль измерения не входит ни в одну целевую величину",
    SelectionReason.SCOPE_MISMATCH: "совокупность не совпадает с целевой величиной профиля",
    SelectionReason.NO_CONCENTRATION: "нет подтверждённой суммарной оценки концентрации",
    SelectionReason.CONCENTRATION_MISMATCH: "N/A расходится с опубликованной концентрацией",
    SelectionReason.EXCLUDED_FLAG: "запись исключена по флагу качества",
}


@dataclass(frozen=True)
class Selection:
    record: CaseRecord
    target_key: str | None
    reason: SelectionReason
    check: ConcentrationCheck
    detail: str = ""

    @property
    def accepted(self) -> bool:
        return self.reason is SelectionReason.ACCEPTED

    @property
    def label(self) -> str:
        base = REASON_LABELS[self.reason]
        return f"{base}: {self.detail}" if self.detail else base


def select_record(record: CaseRecord, config: CaseConfig) -> Selection:
    check = check_record(record, config.concentration)
    rules = config.selection
    if record.record_type != rules.record_type:
        return Selection(record, None, SelectionReason.ITEM_OBSERVATION, check)
    if record.scope in rules.category_scopes:
        return Selection(record, None, SelectionReason.CATEGORY, check, record.scope)
    if not config.profile_in_targets(record.profile):
        return Selection(record, None, SelectionReason.PROFILE_NOT_TARGETED, check, record.profile)
    target = config.target_for(record.profile, record.scope)
    if target is None:
        detail = f"{record.profile} / {record.scope}"
        return Selection(record, None, SelectionReason.SCOPE_MISMATCH, check, detail)
    if record.published_concentration is None:
        return Selection(record, target.key, SelectionReason.NO_CONCENTRATION, check)
    if rules.reject_on_mismatch and check.status is CheckStatus.MISMATCH:
        relative = check.relative_difference
        detail = "" if relative is None else f"расхождение {relative * 100:.1f} %"
        return Selection(record, target.key, SelectionReason.CONCENTRATION_MISMATCH, check, detail)
    excluded = [flag for flag in record.flags if flag in rules.exclude_flags]
    if excluded:
        detail = ", ".join(excluded)
        return Selection(record, target.key, SelectionReason.EXCLUDED_FLAG, check, detail)
    return Selection(record, target.key, SelectionReason.ACCEPTED, check)


def select_records(records: list[CaseRecord], config: CaseConfig) -> list[Selection]:
    return [select_record(record, config) for record in records]
