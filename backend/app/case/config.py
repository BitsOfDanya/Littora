from __future__ import annotations

import datetime as dt
import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Target:
    key: str
    primary: bool
    title: str
    material: str
    size_class: str
    unit: str
    target_scope: tuple[str, ...]
    profiles: tuple[str, ...]
    rationale: str

    def matches(self, profile: str, scope: str) -> bool:
        return profile in self.profiles and scope in self.target_scope


@dataclass(frozen=True)
class SelectionRules:
    record_type: str
    category_scopes: tuple[str, ...]
    exclude_flags: tuple[str, ...]


@dataclass(frozen=True)
class ConcentrationRules:
    match_relative: float
    rounding_relative: float


@dataclass(frozen=True)
class PairingRules:
    catalog: str
    sentinel2: str
    landsat: str
    sentinel2_start: dt.date
    window_days: int
    wide_window_days: int
    max_tile_cloud: float
    max_time_shift_hours: float
    unknown_time_max_days: int
    unknown_time_uncertainty_hours: float
    point_buffer_m: float
    min_strip_width_m: float
    max_footprint_nodata: float
    max_footprint_cloud: float
    min_footprint_water: float
    bright_water_reflectance: float
    max_bright_water: float
    drift_speed_ms: float


@dataclass(frozen=True)
class AnalysisRules:
    collection: str
    max_window_days: int
    max_span_deg: float
    render_max_size: int
    quality_max_size: int
    max_cloud: float
    max_nodata: float
    min_water: float
    scene_cache_seconds: int


@dataclass(frozen=True)
class CaseConfig:
    csv: str
    selection: SelectionRules
    targets: tuple[Target, ...]
    concentration: ConcentrationRules
    pairing: PairingRules
    analysis: AnalysisRules

    @property
    def primary_target(self) -> Target:
        return next(target for target in self.targets if target.primary)

    def target(self, key: str) -> Target | None:
        return next((target for target in self.targets if target.key == key), None)

    def target_for(self, profile: str, scope: str) -> Target | None:
        return next((target for target in self.targets if target.matches(profile, scope)), None)

    def profile_in_targets(self, profile: str) -> bool:
        return any(profile in target.profiles for target in self.targets)


def _target(raw: dict) -> Target:
    return Target(
        key=raw["key"],
        primary=bool(raw.get("primary", False)),
        title=raw["title"],
        material=raw["material"],
        size_class=raw["size_class"],
        unit=raw["unit"],
        target_scope=tuple(raw["target_scope"]),
        profiles=tuple(raw["profiles"]),
        rationale=raw.get("rationale", ""),
    )


def parse_case_config(raw: dict) -> CaseConfig:
    targets = tuple(_target(item) for item in raw["targets"])
    if sum(target.primary for target in targets) != 1:
        raise ValueError("exactly one target must be primary")
    pairing = dict(raw["pairing"])
    pairing["sentinel2_start"] = dt.date.fromisoformat(str(pairing["sentinel2_start"]))
    selection = raw["selection"]
    return CaseConfig(
        csv=raw["data"]["csv"],
        selection=SelectionRules(
            record_type=selection["record_type"],
            category_scopes=tuple(selection["category_scopes"]),
            exclude_flags=tuple(selection.get("exclude_flags", [])),
        ),
        targets=targets,
        concentration=ConcentrationRules(**raw["concentration"]),
        pairing=PairingRules(**pairing),
        analysis=AnalysisRules(**raw["analysis"]),
    )


def load_case_config(path: Path) -> CaseConfig:
    with path.open("rb") as handle:
        return parse_case_config(tomllib.load(handle))
