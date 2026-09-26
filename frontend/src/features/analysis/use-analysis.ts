"use client";

import { useMutation, useMutationState, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo } from "react";
import { findAoi } from "@/config/aois";
import { useCandidates } from "@/data/candidates";
import { useScenes } from "@/data/scenes";
import type { AreaOfInterest } from "@/domain/aoi";
import type { SceneSummary } from "@/domain/scene";
import { useMainMap } from "@/features/map/use-main-map";
import { useSelectedScene } from "@/features/time-rail/use-selected-scene";
import {
  type Analysis,
  type AnalysisCreate,
  type AnalysisFilters,
  type AnalysisListItem,
  createAnalysis,
  getAnalysis,
  getAnalysisConditions,
  listAnalyses,
} from "@/lib/api/analyses";
import { getCaseTargets } from "@/lib/api/case";
import { queryKeys } from "@/lib/query/query-keys";
import { useAnalysisStore } from "@/state/analysis-store";
import { useWorkspaceStore } from "@/state/workspace-store";
import { roundBbox, sameBbox, spanTooLarge, visibleBounds } from "./area";
import { findCurrentMatch, type RealZone, toRealZones } from "./zones";

const HISTORY_STALE_MS = 30_000;

export type RequestPlan = { request: AnalysisCreate } | { problem: string };

export function useCaseTargets() {
  return useQuery({
    queryKey: queryKeys.case.targets,
    queryFn: ({ signal }) => getCaseTargets(signal),
    staleTime: Infinity,
  });
}

export function useCurrentAnalysis() {
  const analysisId = useAnalysisStore((state) => state.analysisId);
  return useQuery({
    queryKey: queryKeys.analyses.detail(analysisId ?? ""),
    queryFn: ({ signal }) => getAnalysis(analysisId ?? "", signal),
    enabled: analysisId !== null,
    staleTime: Infinity,
  });
}

export type AnalysisZones = {
  analysis: Analysis;
  zones: readonly RealZone[];
  threshold: number | null;
};

export function useAnalysisZones(): AnalysisZones | null {
  const demo = useCandidates().origin === "demo";
  const analysis = useCurrentAnalysis().data;
  return useMemo(() => {
    if (demo || !analysis || !analysis.detection.zones.length) return null;
    return {
      analysis,
      zones: toRealZones(analysis.detection.zones),
      threshold: analysis.detection.threshold ?? null,
    };
  }, [demo, analysis]);
}

export function useSelectedZone(): { zone: RealZone; source: AnalysisZones } | null {
  const source = useAnalysisZones();
  const zoneId = useAnalysisStore((state) => state.zoneId);
  if (!source || !zoneId) return null;
  const zone = source.zones.find((entry) => entry.id === zoneId);
  return zone ? { zone, source } : null;
}

const CONDITIONS_RETRY_MS = 60_000;

export function useAnalysisConditions(analysis: Analysis | null) {
  const id = analysis?.scene ? analysis.id : null;
  return useQuery({
    queryKey: queryKeys.analyses.conditions(id ?? ""),
    queryFn: ({ signal }) => getAnalysisConditions(id ?? "", signal),
    enabled: id !== null,
    staleTime: (query) => (query.state.data?.messages.length ? CONDITIONS_RETRY_MS : Infinity),
    retry: false,
  });
}

export function useAnalysisHistory(filters: AnalysisFilters) {
  return useQuery({
    queryKey: queryKeys.analyses.list(filters),
    queryFn: ({ signal }) => listAnalyses(filters, signal),
    staleTime: HISTORY_STALE_MS,
  });
}

const RUN_KEY = ["analyses", "run"] as const;

export function useRunAnalysis() {
  const client = useQueryClient();
  const setAnalysis = useAnalysisStore((state) => state.setAnalysis);
  return useMutation({
    mutationKey: RUN_KEY,
    mutationFn: createAnalysis,
    onSuccess: (analysis: Analysis) => {
      client.setQueryData(queryKeys.analyses.detail(analysis.id), analysis);
      void client.invalidateQueries({ queryKey: ["analyses", "list"] });
      const aoiId = analysis.request.aoi_id;
      if (aoiId === null || aoiId === useWorkspaceStore.getState().aoiId) setAnalysis(analysis.id);
    },
  });
}

export function useAnalysisRunStart(): number | null {
  const starts = useMutationState({
    filters: { mutationKey: RUN_KEY, status: "pending" },
    select: (mutation) => mutation.state.submittedAt,
  });
  return starts.length ? Math.min(...starts) : null;
}

function requestDate(aoi: AreaOfInterest, scene: SceneSummary | null): string {
  if (scene) return scene.acquiredAt.slice(0, 10);
  return aoi.survey?.dates[0] ?? aoi.reference?.date ?? new Date().toISOString().slice(0, 10);
}

export function useRequestPlan() {
  const aoi = findAoi(useWorkspaceStore((state) => state.aoiId));
  const { scene, isDemo } = useSelectedScene();
  const areaMode = useAnalysisStore((state) => state.areaMode);
  const windowDays = useAnalysisStore((state) => state.windowDays);
  const targetKey = useAnalysisStore((state) => state.targetKey);
  const map = useMainMap();
  const realScene = isDemo ? null : scene;

  const plan = useCallback((): RequestPlan => {
    if (!aoi) return { problem: "Район не выбран" };
    const bbox = roundBbox(areaMode === "view" && map ? visibleBounds(map) : aoi.bbox);
    if (spanTooLarge(bbox))
      return { problem: "Вид карты шире 1° — приблизьте карту или выберите весь участок" };
    return {
      request: {
        bbox,
        date: requestDate(aoi, realScene),
        window_days: windowDays,
        aoi_id: aoi.id,
        aoi_name: aoi.name,
        scene_id: realScene?.id ?? null,
        target: targetKey ?? aoi.survey?.target ?? null,
      },
    };
  }, [aoi, areaMode, map, realScene, windowDays, targetKey]);

  return { aoi, scene: realScene, areaMode, windowDays, plan };
}

export function matchesRequest(
  item: Pick<AnalysisListItem, "request">,
  request: AnalysisCreate,
  primaryTarget: string | undefined,
): boolean {
  const saved = item.request;
  return (
    sameBbox(saved.bbox, request.bbox) &&
    saved.date === request.date &&
    saved.window_days === request.window_days &&
    (saved.scene_id ?? null) === (request.scene_id ?? null) &&
    saved.target === (request.target ?? primaryTarget)
  );
}

export function useSavedMatch(): AnalysisListItem | null {
  const aoiId = useWorkspaceStore((state) => state.aoiId);
  const areaMode = useAnalysisStore((state) => state.areaMode);
  const primary = useCaseTargets().data?.primary;
  const history = useAnalysisHistory({ aoiId });
  const { plan } = useRequestPlan();
  const planned = areaMode === "aoi" ? plan() : null;
  const key = planned && "request" in planned ? JSON.stringify(planned.request) : null;

  return useMemo(() => {
    if (!key || !history.data) return null;
    const request = JSON.parse(key) as AnalysisCreate;
    return findCurrentMatch(history.data, (item) => matchesRequest(item, request, primary));
  }, [key, history.data, primary]);
}

export function useOpenSavedMatch() {
  const match = useSavedMatch();
  const setAnalysis = useAnalysisStore((state) => state.setAnalysis);
  useEffect(() => {
    if (match && useAnalysisStore.getState().analysisId === null) setAnalysis(match.id);
  }, [match, setAnalysis]);
}

export function latestZonesAnalysis(
  items: readonly AnalysisListItem[],
  aoiId: string,
): AnalysisListItem | null {
  return (
    items.find((item) => !item.stale && (item.zones ?? 0) > 0 && item.request.aoi_id === aoiId) ??
    null
  );
}

export function useAdoptSavedAnalysis() {
  const demo = useWorkspaceStore((state) => state.demoFixtures);
  const aoiId = useWorkspaceStore((state) => state.aoiId);
  const analysisId = useAnalysisStore((state) => state.analysisId);
  const setAnalysis = useAnalysisStore((state) => state.setAnalysis);
  const history = useAnalysisHistory({ aoiId });
  const pick = useMemo(
    () => (history.data ? latestZonesAnalysis(history.data, aoiId) : null),
    [history.data, aoiId],
  );
  useEffect(() => {
    if (!demo && analysisId === null && pick) setAnalysis(pick.id);
  }, [demo, analysisId, pick, setAnalysis]);
}

export function defaultScene(
  scenes: readonly SceneSummary[],
  surveyDay: string | null,
): SceneSummary | undefined {
  if (surveyDay) {
    const sameDay = scenes.filter((scene) => scene.acquiredAt.startsWith(surveyDay));
    return [...sameDay].sort(
      (a, b) => (b.areaCoverage ?? 0) - (a.areaCoverage ?? 0) || a.cloudCover - b.cloudCover,
    )[0];
  }
  return scenes.findLast((scene) => scene.usability === "usable");
}

export function useSurveySceneDefault() {
  const aoi = findAoi(useWorkspaceStore((state) => state.aoiId));
  const sceneId = useWorkspaceStore((state) => state.sceneId);
  const selectScene = useWorkspaceStore((state) => state.selectScene);
  const scenes = useScenes();
  const list = scenes.origin === "api" ? scenes.data : null;

  useEffect(() => {
    if (!list || !aoi) return;
    if (sceneId && list.some((scene) => scene.id === sceneId)) return;
    const best = defaultScene(list, aoi.survey?.dates[0] ?? aoi.reference?.date ?? null);
    if (best) selectScene(best.id);
  }, [aoi, list, sceneId, selectScene]);
}
