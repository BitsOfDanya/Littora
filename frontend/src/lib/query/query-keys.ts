import type { AnalysisFilters } from "@/lib/api/analyses";
import type { ObservationQuery } from "@/lib/api/case";
import type { ReviewFilters } from "@/lib/api/review";
import type { SceneQuery } from "@/lib/api/scenes";
import type { TimelineQuery } from "@/lib/api/timeline";

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
  timeline: {
    all: ["timeline"] as const,
    series: (query: TimelineQuery | null) => ["timeline", "series", query] as const,
    compare: (before: string, after: string) => ["timeline", "compare", before, after] as const,
  },
  models: ["models"] as const,
  analyses: {
    all: ["analyses"] as const,
    detail: (id: string) => ["analyses", "detail", id] as const,
    list: (filters: AnalysisFilters) => ["analyses", "list", filters] as const,
    drift: (id: string) => ["analyses", "drift", id] as const,
    survey: (id: string) => ["analyses", "survey", id] as const,
    conditions: (id: string) => ["analyses", "conditions", id] as const,
  },
  reviews: {
    all: ["reviews"] as const,
    analysis: (id: string) => ["reviews", "analysis", id] as const,
    list: (filters: ReviewFilters) => ["reviews", "list", filters] as const,
  },
};
