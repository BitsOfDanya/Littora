import type { SceneSummary } from "@/domain/scene";
import type { SeriesPoint } from "@/features/inspector/parts/observation-series";
import type { TimelinePass, TimelinePassAnalysis, TimelineRun } from "@/lib/api/timeline";
import type { ComparePair } from "./compare-model";

export type LivePasses = ReadonlyMap<string, TimelinePass>;

export type PassVerdict = "detected" | "not-detected" | "insufficient" | "pending";

export function passVerdict(analysis: TimelinePassAnalysis | null | undefined): PassVerdict {
  if (!analysis) return "pending";
  if (analysis.zone_count === null) return "insufficient";
  return analysis.zone_count > 0 ? "detected" : "not-detected";
}

export function analysisOf(passes: LivePasses, sceneId: string): TimelinePassAnalysis | null {
  return passes.get(sceneId)?.analysis ?? null;
}

export function liveSeries(scenes: readonly SceneSummary[], passes: LivePasses): SeriesPoint[] {
  return scenes.flatMap((scene): SeriesPoint[] => {
    const analysis = analysisOf(passes, scene.id);
    const verdict = passVerdict(analysis);
    const base = { id: scene.id, time: scene.acquiredAt, cloudCover: scene.cloudCover };
    if (verdict === "pending") return [];
    if (verdict === "insufficient") return [{ ...base, state: "cloudy" }];
    if (verdict === "not-detected") return [{ ...base, state: "not-found", value: 0 }];
    return [{ ...base, state: "observed", value: Math.round((analysis?.area_km2 ?? 0) * 1e6) }];
  });
}

export function missingInPair(pair: ComparePair, passes: LivePasses): string[] {
  return [pair.a, pair.b]
    .filter((scene) => analysisOf(passes, scene.id) === null)
    .map((scene) => scene.id);
}

export function openUsable(scenes: readonly SceneSummary[], passes: LivePasses): number {
  return scenes.filter((scene) => {
    const analysis = analysisOf(passes, scene.id);
    return scene.usability !== "unusable" && (analysis === null || analysis.retryable);
  }).length;
}

export function runStateOf(
  run: TimelineRun | null | undefined,
  sceneId: string,
): TimelineRun["items"][number]["state"] | null {
  return run?.items.find((item) => item.scene_id === sceneId)?.state ?? null;
}
