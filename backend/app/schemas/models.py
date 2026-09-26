from pydantic import BaseModel

from app.schemas.drift import DriftValidation

Interval = tuple[float, float]


class Metrics(BaseModel):
    precision: float
    recall: float
    f1: float
    iou: float
    pr_auc: float | None = None


class MetricIntervals(BaseModel):
    precision: Interval
    recall: Interval
    f1: Interval
    iou: Interval


class ClassFalsePositives(BaseModel):
    label: str
    pixels: int
    false_positives: int


class SplitEvaluation(BaseModel):
    pixels: int
    positives: int
    true_positives: int | None
    false_positives: int | None
    false_negatives: int | None
    metrics: Metrics
    ci95: MetricIntervals | None
    false_positives_by_class: list[ClassFalsePositives]


class Postprocessing(BaseModel):
    threshold: float
    min_pixels: int
    scene_classes: bool
    ship_veto: bool
    test: Metrics | None


class DetectorRun(BaseModel):
    name: str
    config_sha256: str | None
    method: str
    kind: str | None
    loss: str | None
    data: str
    split: str | None
    members: list[str]
    weights: list[float]
    source_run: str | None
    threshold: float
    threshold_source: str | None
    tta: bool | None
    inputs: list[str] | None
    val: SplitEvaluation | None
    test: SplitEvaluation
    postprocessing: Postprocessing | None
    unlabeled_alarms_per_100km2: float | None
    in_service: bool


class DetectorService(BaseModel):
    name: str
    threshold: float
    min_pixels: int
    bands: list[str]
    patch: int | None
    stride: int | None
    data: str | None
    split: str | None
    sea_mask: str | None
    validation: str | None
    test: Metrics | None
    test_ci95: MetricIntervals | None
    postprocessed_test: Metrics | None
    service_test: Metrics | None = None
    service_mode: str | None = None
    calibration: str | None = None


class DetectorTestSet(BaseModel):
    dataset: str
    data: str
    split: str
    patches: int | None
    scenes: int | None
    pixels: int
    positives: int


class RegionResult(BaseModel):
    region: str
    positives: int
    threshold: float | None
    metrics: Metrics


class LeaveRegionOut(BaseModel):
    run: str
    protocol: str | None
    regions: list[RegionResult]
    pooled: Metrics


class NegativeClass(BaseModel):
    label: str
    polygons: int
    pixels: int
    area_km2: float
    alarm_pixels: int
    polygons_with_alarm: int


class NegativeScene(BaseModel):
    aoi: str
    scene_id: str
    pixels: int
    detected_pixels: int
    zones: int


class BlackSeaNegatives(BaseModel):
    run: str
    collection: str | None
    definition: str | None
    pixels: int
    alarm_pixels: int
    classes: list[NegativeClass]
    scenes: list[NegativeScene]


class DetectionRate(BaseModel):
    group: str
    targets: int
    detected: int
    rate: float
    ci95: Interval | None
    zone_detected: int | None


class PlpBackground(BaseModel):
    windows: int
    water_km2: float
    zones: int
    zones_per_100_km2: float
    ring_km2: float
    ring_alarm_pixels: int


class PlasticLitterProject(BaseModel):
    description: str | None
    threshold: str | None
    targets: int
    usable: int
    groups: list[DetectionRate]
    by_size: list[DetectionRate]
    background: PlpBackground | None


class FlagShare(BaseModel):
    part: str
    group: str
    objects: int
    flagged: int
    share: float | None


class FlagDiscrimination(BaseModel):
    part: str
    measure: str
    value: float | None
    ci95: Interval | None


class ZoneFlagCheck(BaseModel):
    kind: str
    title: str
    rule: str
    in_service: bool
    shares: list[FlagShare]
    discrimination: list[FlagDiscrimination] = []


class CollectionCheckRow(BaseModel):
    run: str
    in_service: bool
    part: str
    mode: str
    patches: int
    scenes: int
    c1_f1: float
    c1_ci95: Interval | None
    l2a_f1: float
    l2a_ci95: Interval | None
    difference: float
    difference_ci95: Interval | None


class CollectionCheck(BaseModel):
    alignment: str
    rule: str
    chosen: str
    rows: list[CollectionCheckRow]


class DetectorChecks(BaseModel):
    domain_shift: list[DetectorRun]
    leave_region_out: list[LeaveRegionOut]
    black_sea_negatives: BlackSeaNegatives | None
    plp: PlasticLitterProject | None
    zone_flags: list[ZoneFlagCheck] = []
    collection: CollectionCheck | None = None


class DetectorReport(BaseModel):
    service: DetectorService | None
    test_set: DetectorTestSet | None
    runs: list[DetectorRun]
    checks: DetectorChecks


class MeanSd(BaseModel):
    mean: float
    sd: float | None


class Difference(BaseModel):
    mean: float
    confidence: float
    ci: Interval
    relative: float | None
    relative_ci: Interval | None


class ConcentrationEvaluation(BaseModel):
    report: str
    role: str | None
    selection: str | None
    repetitions: int | None
    baseline_mae: MeanSd
    baseline_rmse: MeanSd
    nested_mae: MeanSd
    nested_rmse: MeanSd
    nested_coverage: MeanSd | None
    difference_mae: Difference | None
    difference_rmse: Difference | None
    gain_over_median: bool


class ServedConcentration(BaseModel):
    model: str
    kind: str | None
    gain_over_median: bool
    reason: str | None
    value: float | None
    unit: str | None
    coverage_nominal: float | None
    coverage_empirical: float | None
    rule: str | None


class ConcentrationProfile(BaseModel):
    profile: str
    target_key: str | None
    events: int | None
    survey_days: int | None
    served: ServedConcentration | None
    evaluations: list[ConcentrationEvaluation]


class Correlation(BaseModel):
    feature: str
    spearman: float | None
    p_value: float | None


class SatellitePair(BaseModel):
    event_id: str
    scene_id: str
    concentration: float | None
    water_pixels: int | None
    detected_share: float | None
    probability_p99: float | None
    fdi_p99: float | None


class SatelliteLink(BaseModel):
    detector: str | None
    events: int
    correlations: list[Correlation]
    pairs: list[SatellitePair] = []


class ConcentrationReport(BaseModel):
    profiles: list[ConcentrationProfile]
    satellite_link: SatelliteLink | None


class DriftForcing(BaseModel):
    currents: str
    waves: str
    wind: list[str]


class DriftMethod(BaseModel):
    model: str
    status: str
    label: str
    reason: str
    velocity: str
    integration: str
    windages: list[float]
    stokes: list[bool]
    particles: int
    members: int
    diffusivity_m2s: float
    horizons_h: list[int]
    max_hours: int
    max_hindcast_hours: int
    forcing: DriftForcing
    envelope: str | None = None
    envelope_spread: str | None = None
    envelope_domain_margin_km: float | None = None
    validation: DriftValidation | None = None


class ModelsResponse(BaseModel):
    detector: DetectorReport | None
    concentration: ConcentrationReport | None
    drift: DriftMethod | None
    sources: list[str]
