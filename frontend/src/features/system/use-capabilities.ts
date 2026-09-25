"use client";

import { useQuery } from "@tanstack/react-query";
import { capabilityKeySchema, type CapabilityKey, getMeta } from "@/lib/api/system";
import { queryKeys } from "@/lib/query/query-keys";

export type CapabilityAvailability = "available" | "planned" | "unknown";

export const CAPABILITY_KEYS: readonly CapabilityKey[] = capabilityKeySchema.options;

export const CAPABILITY_LABELS: Record<CapabilityKey, string> = {
  scene_catalog: "Каталог снимков",
  field_observations: "Натурные измерения кейса",
  pair_registry: "Реестр пар снимок — измерение",
  quality_masks: "Маска качества снимка",
  analysis_requests: "Анализ района",
  export: "Выгрузка GeoJSON и CSV",
  debris_detection: "Детекция мусора",
  segmentation: "Сегментация пятен",
  coverage_estimation: "Доля покрытия пикселя",
  spectral_composites: "Спектральные композиты",
  concentration_model: "Концентрация, шт./км²",
  change_tracking: "Сравнение по датам",
  drift_forecast: "Прогноз дрейфа",
  survey_planning: "Планирование обследований",
  model_evaluation: "Оценка моделей",
};

export function useApiMeta() {
  return useQuery({
    queryKey: queryKeys.system.meta,
    queryFn: ({ signal }) => getMeta(signal),
    staleTime: 5 * 60_000,
  });
}

export function useCapability(key: CapabilityKey): CapabilityAvailability {
  const { data } = useApiMeta();
  return data?.capabilities.find((capability) => capability.key === key)?.status ?? "unknown";
}

export type CapabilitySummary = {
  status: "loading" | "error" | "ready";
  availableCount: number;
  total: number;
  entries: readonly { key: CapabilityKey; availability: CapabilityAvailability }[];
};

export function useCapabilitySummary(): CapabilitySummary {
  const { data, isPending, isError } = useApiMeta();
  const entries = CAPABILITY_KEYS.map((key) => ({
    key,
    availability:
      data?.capabilities.find((capability) => capability.key === key)?.status ??
      ("unknown" as const),
  }));
  return {
    status: isError ? "error" : isPending ? "loading" : "ready",
    availableCount: entries.filter((entry) => entry.availability === "available").length,
    total: CAPABILITY_KEYS.length,
    entries,
  };
}
