import type { WorkspaceModeId } from "./modes";
import type { CapabilityKey } from "@/lib/api/system";

export type LayerGroupId =
  "scene" | "analysis" | "results" | "conditions" | "context" | "compare" | "forecast" | "survey";

export type LegendKind =
  | "composite"
  | "coverage-ramp"
  | "confidence-lines"
  | "uncertainty-hatch"
  | "hotspot-cells"
  | "nodata-hatch"
  | "footprint-line"
  | "analysis-area"
  | "observation-marks"
  | "aoi-line"
  | "graticule"
  | "labels"
  | "delta-ramp"
  | "envelopes"
  | "median-path"
  | "hindcast-path"
  | "particles"
  | "beaching"
  | "target-rings"
  | "route-line"
  | "search-radius";

export type CompositeLayerId =
  "scene-true-color" | "scene-false-color" | "scene-fdi" | "scene-ndvi";

export type LayerId =
  | CompositeLayerId
  | "coverage"
  | "candidates"
  | "uncertainty"
  | "hotspots"
  | "no-data"
  | "scene-footprint"
  | "analysis-area"
  | "field-observations"
  | "aoi-boundary"
  | "graticule"
  | "labels"
  | "change-delta"
  | "forecast-envelopes"
  | "forecast-median"
  | "forecast-hindcast"
  | "particles"
  | "beaching"
  | "survey-targets"
  | "survey-route"
  | "search-radius";

export type LegacyLayerId = "currents" | "drift-forecast";

export type MapLayerId = LayerId | LegacyLayerId;

export type MapModeId = Exclude<WorkspaceModeId, "models">;

export type LayerDefinition = {
  id: LayerId;
  label: string;
  group: LayerGroupId;
  capability: CapabilityKey | null;
  hasDemo: boolean;
  modes: readonly MapModeId[];
  legend: LegendKind;
  plannedReason?: string;
  hotkey?: string;
};

export const MAP_MODES: readonly MapModeId[] = ["monitor", "timeline", "forecast", "survey"];

export const LAYER_GROUP_LABELS: Record<LayerGroupId, string> = {
  scene: "Снимок даты",
  analysis: "Анализ района",
  results: "Результаты модели",
  conditions: "Условия наблюдения",
  context: "Контекст",
  compare: "Сравнение дат",
  forecast: "Прогноз дрейфа",
  survey: "Обследование",
};

const ALL_MAP_MODES = MAP_MODES;
const SCENE_REASON = "Нужен каталог сцен Sentinel-2 L2A — пока показана подложка.";
const COMPOSITE_REASON =
  "Сейчас строится только RGB-снимок даты; композиты и индексы — следующий этап.";
const FORECAST_REASON = "Нужны поля течений CMEMS, ветер GFS и выбранное пятно.";
const SURVEY_REASON = "Появится с модулем планирования обследований.";

export const LAYERS: readonly LayerDefinition[] = [
  {
    id: "scene-true-color",
    label: "RGB",
    group: "scene",
    capability: "scene_catalog",
    hasDemo: false,
    modes: ["monitor"],
    legend: "composite",
    plannedReason: SCENE_REASON,
  },
  {
    id: "scene-false-color",
    label: "Ложные",
    group: "scene",
    capability: "spectral_composites",
    hasDemo: false,
    modes: ["monitor"],
    legend: "composite",
    plannedReason: COMPOSITE_REASON,
  },
  {
    id: "scene-fdi",
    label: "FDI",
    group: "scene",
    capability: "spectral_composites",
    hasDemo: false,
    modes: ["monitor"],
    legend: "composite",
    plannedReason: COMPOSITE_REASON,
  },
  {
    id: "scene-ndvi",
    label: "NDVI",
    group: "scene",
    capability: "spectral_composites",
    hasDemo: false,
    modes: ["monitor"],
    legend: "composite",
    plannedReason: COMPOSITE_REASON,
  },
  {
    id: "analysis-area",
    label: "Район анализа и статус",
    group: "analysis",
    capability: "analysis_requests",
    hasDemo: false,
    modes: ["monitor"],
    legend: "analysis-area",
    plannedReason: "Нужен сервис анализа района на сервере.",
  },
  {
    id: "field-observations",
    label: "Полевые измерения, шт./км²",
    group: "analysis",
    capability: "field_observations",
    hasDemo: false,
    modes: ["monitor"],
    legend: "observation-marks",
    plannedReason: "Нужны данные кейса в data/case на сервере.",
  },
  {
    id: "coverage",
    label: "Доля покрытия пикселя",
    group: "results",
    capability: "coverage_estimation",
    hasDemo: true,
    modes: ["monitor", "timeline"],
    legend: "coverage-ramp",
    plannedReason: "Появится с моделью оценки доли покрытия пикселя 10\u202Fм.",
  },
  {
    id: "candidates",
    label: "Пятна-кандидаты",
    group: "results",
    capability: "segmentation",
    hasDemo: true,
    modes: ALL_MAP_MODES,
    legend: "confidence-lines",
    plannedReason: "Появятся с моделью сегментации пятен на снимке даты.",
  },
  {
    id: "uncertainty",
    label: "Неопределённость",
    group: "results",
    capability: "debris_detection",
    hasDemo: true,
    modes: ["monitor", "survey"],
    legend: "uncertainty-hatch",
    plannedReason: "Появится вместе с детекцией: где модель менее уверена.",
  },
  {
    id: "hotspots",
    label: "Горячие точки",
    group: "results",
    capability: "debris_detection",
    hasDemo: true,
    modes: ["monitor"],
    legend: "hotspot-cells",
    plannedReason: "Появятся вместе с детекцией.",
  },
  {
    id: "no-data",
    label: "Облака, блики, нет данных",
    group: "conditions",
    capability: "quality_masks",
    hasDemo: true,
    modes: ["monitor", "timeline"],
    legend: "nodata-hatch",
    plannedReason: "Маска облаков и бликов строится по слою SCL снимка при анализе района.",
  },
  {
    id: "scene-footprint",
    label: "Контур сцены",
    group: "conditions",
    capability: "scene_catalog",
    hasDemo: true,
    modes: ["monitor", "timeline"],
    legend: "footprint-line",
    plannedReason: "Контур приходит вместе со сценой из каталога.",
  },
  {
    id: "aoi-boundary",
    label: "Граница района",
    group: "context",
    capability: null,
    hasDemo: false,
    modes: ALL_MAP_MODES,
    legend: "aoi-line",
  },
  {
    id: "graticule",
    label: "Сетка и рамка",
    group: "context",
    capability: null,
    hasDemo: false,
    modes: ALL_MAP_MODES,
    legend: "graticule",
    hotkey: "G",
  },
  {
    id: "labels",
    label: "Подписи",
    group: "context",
    capability: null,
    hasDemo: false,
    modes: ALL_MAP_MODES,
    legend: "labels",
  },
  {
    id: "change-delta",
    label: "Δ покрытия A → B",
    group: "compare",
    capability: "change_tracking",
    hasDemo: false,
    modes: ["timeline"],
    legend: "delta-ramp",
    plannedReason: "Нужна детекция по обеим датам A и B.",
  },
  {
    id: "forecast-envelopes",
    label: "Облако вероятности (90\u202F% ансамбля)",
    group: "forecast",
    capability: "drift_forecast",
    hasDemo: true,
    modes: ["forecast"],
    legend: "envelopes",
    plannedReason: FORECAST_REASON,
  },
  {
    id: "forecast-median",
    label: "Медиана траектории",
    group: "forecast",
    capability: "drift_forecast",
    hasDemo: true,
    modes: ["forecast"],
    legend: "median-path",
    plannedReason: FORECAST_REASON,
  },
  {
    id: "forecast-hindcast",
    label: "Обратный дрейф",
    group: "forecast",
    capability: "drift_forecast",
    hasDemo: true,
    modes: ["forecast"],
    legend: "hindcast-path",
    plannedReason: FORECAST_REASON,
  },
  {
    id: "particles",
    label: "Частицы течений",
    group: "forecast",
    capability: "drift_forecast",
    hasDemo: true,
    modes: ["forecast"],
    legend: "particles",
    plannedReason: "Нужны поля течений CMEMS GLO-PHY.",
    hotkey: "M",
  },
  {
    id: "beaching",
    label: "Берег: риск выноса",
    group: "forecast",
    capability: "drift_forecast",
    hasDemo: true,
    modes: ["forecast"],
    legend: "beaching",
    plannedReason: FORECAST_REASON,
  },
  {
    id: "survey-targets",
    label: "Цели",
    group: "survey",
    capability: "survey_planning",
    hasDemo: true,
    modes: ["survey"],
    legend: "target-rings",
    plannedReason: SURVEY_REASON,
  },
  {
    id: "survey-route",
    label: "Маршрут",
    group: "survey",
    capability: "survey_planning",
    hasDemo: true,
    modes: ["survey"],
    legend: "route-line",
    plannedReason: SURVEY_REASON,
  },
  {
    id: "search-radius",
    label: "Радиус поиска",
    group: "survey",
    capability: "survey_planning",
    hasDemo: true,
    modes: ["survey"],
    legend: "search-radius",
    plannedReason: SURVEY_REASON,
  },
];

export const COMPOSITE_LAYER_IDS: readonly CompositeLayerId[] = [
  "scene-true-color",
  "scene-false-color",
  "scene-fdi",
  "scene-ndvi",
];

export const LEGACY_LAYER_ALIASES: Record<LegacyLayerId, LayerId> = {
  currents: "particles",
  "drift-forecast": "forecast-envelopes",
};

export const DEFAULT_VISIBLE_LAYERS: readonly LayerId[] = [
  "analysis-area",
  "field-observations",
  "coverage",
  "candidates",
  "hotspots",
  "no-data",
  "scene-footprint",
  "aoi-boundary",
  "graticule",
  "labels",
  "change-delta",
  "forecast-envelopes",
  "forecast-median",
  "forecast-hindcast",
  "particles",
  "beaching",
  "survey-targets",
  "survey-route",
  "search-radius",
];

function isLegacyLayerId(id: MapLayerId): id is LegacyLayerId {
  return Object.hasOwn(LEGACY_LAYER_ALIASES, id);
}

export function resolveLayerId(id: MapLayerId): LayerId {
  return isLegacyLayerId(id) ? LEGACY_LAYER_ALIASES[id] : id;
}

export function findLayer(id: MapLayerId): LayerDefinition | undefined {
  const resolved = resolveLayerId(id);
  return LAYERS.find((layer) => layer.id === resolved);
}

export function isMapMode(mode: WorkspaceModeId): mode is MapModeId {
  return mode !== "models";
}

export function layersForMode(mode: WorkspaceModeId): LayerDefinition[] {
  return isMapMode(mode) ? LAYERS.filter((layer) => layer.modes.includes(mode)) : [];
}

export function layersInGroup(mode: MapModeId, group: LayerGroupId): LayerDefinition[] {
  return LAYERS.filter((layer) => layer.group === group && layer.modes.includes(mode));
}
