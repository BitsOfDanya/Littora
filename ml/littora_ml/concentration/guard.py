from __future__ import annotations

from littora_ml.audit.case_audit import leakage_audit, load_case
from littora_ml.concentration.features import FEATURE_GROUPS, FEATURE_SOURCES, OBSERVED_AT

BLOCKED_ROLES = ("target", "forbidden_leakage", "survey_only", "identifier")
MODEL_TABLE_BLOCKED = ("concentration", "sample_id", "event_id", "source_id", "target_key")


class LeakageError(RuntimeError):
    pass


def blocked_columns() -> set[str]:
    audit = leakage_audit(load_case())
    roles = {column for role in BLOCKED_ROLES for column in audit["roles"].get(role, [])}
    return roles | set(MODEL_TABLE_BLOCKED)


def provenance(columns: list[str]) -> dict[str, dict]:
    group_of = {column: group for group, names in FEATURE_GROUPS.items() for column in names}
    return {
        column: {"group": group_of[column], **FEATURE_SOURCES[group_of[column]]}
        for column in sorted(set(columns))
    }


def check_features(columns: list[str], blocked: set[str] | None = None) -> dict:
    allowed = {column for group in FEATURE_GROUPS.values() for column in group}
    blocked = blocked if blocked is not None else blocked_columns()
    violations = sorted(c for c in columns if c in blocked or c not in allowed)
    if violations:
        raise LeakageError(f"запрещённые или неописанные признаки: {', '.join(violations)}")
    return {
        "checked": sorted(set(columns)),
        "blocked_in_case_data": sorted(blocked),
        "provenance": provenance(columns),
        "allowed_time_source": {"observed_at": OBSERVED_AT},
    }
