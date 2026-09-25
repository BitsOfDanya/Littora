"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo } from "react";
import { findAoi } from "@/config/aois";
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
  listAnalyses,
} from "@/lib/api/analyses";
import { getCaseTargets } from "@/lib/api/case";
import { queryKeys } from "@/lib/query/query-keys";
import { useAnalysisStore } from "@/state/analysis-store";
import { useWorkspaceStore } from "@/state/workspace-store";
import { roundBbox, sameBbox, spanTooLarge, visibleBounds } from "./area";

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

export function useAnalysisHistory(filters: AnalysisFilters) {
  return useQuery({
    queryKey: queryKeys.analyses.list(filters),
    queryFn: ({ signal }) => listAnalyses(filters, signal),
    staleTime: HISTORY_STALE_MS,
  });
}

export function useRunAnalysis() {
  const client = useQueryClient();
  const setAnalysis = useAnalysisStore((state) => state.setAnalysis);
  return useMutation({
    mutationFn: createAnalysis,
    onSuccess: (analysis: Analysis) => {
      client.setQueryData(queryKeys.analyses.detail(analysis.id), analysis);
      void client.invalidateQueries({ queryKey: ["analyses", "list"] });
      setAnalysis(analysis.id);
    },
  });
}

function requestDate(aoi: AreaOfInterest, scene: SceneSummary | null): string {
  if (scene) return scene.acquiredAt.slice(0, 10);
  return aoi.survey?.dates[0] ?? new Date().toISOString().slice(0, 10);
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
        target: targetKey,
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
    return history.data.find((item) => matchesRequest(item, request, primary)) ?? null;
  }, [key, history.data, primary]);
}

export function useOpenSavedMatch() {
  const match = useSavedMatch();
  const setAnalysis = useAnalysisStore((state) => state.setAnalysis);
  useEffect(() => {
    if (match && useAnalysisStore.getState().analysisId === null) setAnalysis(match.id);
  }, [match, setAnalysis]);
}

export function useSurveySceneDefault() {
  const aoi = findAoi(useWorkspaceStore((state) => state.aoiId));
  const sceneId = useWorkspaceStore((state) => state.sceneId);
  const selectScene = useWorkspaceStore((state) => state.selectScene);
  const scenes = useScenes();
  const list = scenes.origin === "api" ? scenes.data : null;

  useEffect(() => {
    const surveyDay = aoi?.survey?.dates[0];
    if (!list || !surveyDay) return;
    if (sceneId && list.some((scene) => scene.id === sceneId)) return;
    const sameDay = list.filter((scene) => scene.acquiredAt.startsWith(surveyDay));
    const best = [...sameDay].sort(
      (a, b) => (b.areaCoverage ?? 0) - (a.areaCoverage ?? 0) || a.cloudCover - b.cloudCover,
    )[0];
    if (best) selectScene(best.id);
  }, [aoi, list, sceneId, selectScene]);
}
