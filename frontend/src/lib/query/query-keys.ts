import type { AnalysisFilters } from "@/lib/api/analyses";
import type { ObservationQuery } from "@/lib/api/case";
import type { SceneQuery } from "@/lib/api/scenes";

export const queryKeys = {
  system: {
    health: ["system", "health"] as const,
    meta: ["system", "meta"] as const,
  },
  case: {
    targets: ["case", "targets"] as const,
    observations: (query: ObservationQuery) => ["case", "observations", query] as const,
  },
  scenes: (query: SceneQuery | null) => ["scenes", query] as const,
  analyses: {
    all: ["analyses"] as const,
    detail: (id: string) => ["analyses", "detail", id] as const,
    list: (filters: AnalysisFilters) => ["analyses", "list", filters] as const,
  },
};
