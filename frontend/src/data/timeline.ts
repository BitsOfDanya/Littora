"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { findAoi } from "@/config/aois";
import type { LngLat } from "@/domain/geo";
import type { Estimate } from "@/domain/measurement";
import { DEMO_CANDIDATE_HISTORIES } from "@/demo/timeline";
import { describeApiError } from "@/lib/api/errors";
import {
  createTimelineRun,
  getTimeline,
  getTimelineCompare,
  type Timeline,
  type TimelinePass,
  type TimelineQuery,
  type TimelineRun,
} from "@/lib/api/timeline";
import { queryKeys } from "@/lib/query/query-keys";
import { useWorkspaceStore } from "@/state/workspace-store";
import { sceneQueryFor } from "./scenes";
import { useDemoSourced } from "./use-sourced";

export type PassState = "found" | "not-found" | "cloudy" | "no-data";

export type CandidatePass = {
  sceneId: string;
  observedAt: string;
  state: PassState;
  geometry: GeoJSON.Polygon | null;
  centroid: LngLat | null;
  areaM2: number | null;
  coverage: Estimate | null;
};

export type CandidateHistory = {
  candidateId: string;
  passes: readonly CandidatePass[];
};

export const TIMELINE_DEMO_SOURCE = "src/demo/timeline.ts";

export const useCandidateHistories = () => useDemoSourced(DEMO_CANDIDATE_HISTORIES);

const RUN_POLL_MS = 3000;
const TIMELINE_STALE_MS = 60_000;

export type LiveTimeline =
  | { status: "demo" }
  | { status: "unavailable" }
  | { status: "loading" }
  | { status: "error"; message: string; retry: () => void }
  | { status: "ready"; timeline: Timeline; bySceneId: ReadonlyMap<string, TimelinePass> };

export function isRunActive(run: TimelineRun | null | undefined): boolean {
  return run?.status === "queued" || run?.status === "running";
}

export function timelineQueryFor(aoiId: string, now: number): TimelineQuery | null {
  const scenes = sceneQueryFor(aoiId, now);
  if (!scenes) return null;
  return { ...scenes, target: findAoi(aoiId)?.survey?.target ?? null };
}

function useTimelineQuery(): TimelineQuery | null {
  const aoiId = useWorkspaceStore((state) => state.aoiId);
  const [mountedAt] = useState(() => Date.now());
  return useMemo(() => timelineQueryFor(aoiId, mountedAt), [aoiId, mountedAt]);
}

export function useRefreshAfterRun(run: TimelineRun | null | undefined): void {
  const client = useQueryClient();
  const active = isRunActive(run);
  const completed = run?.completed ?? 0;
  const seen = useRef({ active, completed });
  useEffect(() => {
    const before = seen.current;
    seen.current = { active, completed };
    if ((before.active && !active) || completed > before.completed)
      void client.invalidateQueries({ queryKey: ["analyses", "list"] });
  }, [active, completed, client]);
}

export function useLiveTimeline(): LiveTimeline {
  const demo = useDemoSourced(null);
  const query = useTimelineQuery();
  const result = useQuery({
    queryKey: queryKeys.timeline.series(query),
    queryFn: ({ signal }) =>
      query ? getTimeline(query, signal) : Promise.reject(new Error("Район не выбран")),
    enabled: demo.origin !== "demo" && query !== null,
    staleTime: TIMELINE_STALE_MS,
    refetchInterval: (current) => (isRunActive(current.state.data?.run) ? RUN_POLL_MS : false),
  });
  const bySceneId = useMemo(
    () => new Map((result.data?.passes ?? []).map((pass) => [pass.scene.id, pass])),
    [result.data],
  );
  if (demo.origin === "demo") return { status: "demo" };
  if (!query) return { status: "unavailable" };
  if (result.data) return { status: "ready", timeline: result.data, bySceneId };
  if (result.isError)
    return {
      status: "error",
      message: describeApiError(result.error),
      retry: () => void result.refetch(),
    };
  return { status: "loading" };
}

export function useStartTimelineRun() {
  const client = useQueryClient();
  const query = useTimelineQuery();
  const aoiId = useWorkspaceStore((state) => state.aoiId);
  const mutation = useMutation({
    mutationFn: (options: { sceneIds?: readonly string[]; maxPasses?: number }) => {
      if (!query) return Promise.reject(new Error("Район не выбран"));
      return createTimelineRun({
        bbox: query.bbox,
        date_from: query.dateFrom,
        date_to: query.dateTo,
        aoi_id: query.aoiId,
        aoi_name: findAoi(aoiId)?.name ?? null,
        target: query.target ?? null,
        max_passes: options.maxPasses,
        scene_ids: options.sceneIds ? [...options.sceneIds] : null,
      });
    },
    onSuccess: () => void client.invalidateQueries({ queryKey: queryKeys.timeline.all }),
  });
  return {
    start: (options: { sceneIds?: readonly string[]; maxPasses?: number } = {}) =>
      mutation.mutate(options),
    pending: mutation.isPending,
    error: mutation.isError ? describeApiError(mutation.error) : null,
  };
}

export function useTimelineCompare(beforeId: string | null, afterId: string | null) {
  return useQuery({
    queryKey: queryKeys.timeline.compare(beforeId ?? "", afterId ?? ""),
    queryFn: ({ signal }) => getTimelineCompare(beforeId ?? "", afterId ?? "", signal),
    enabled: Boolean(beforeId && afterId && beforeId !== afterId),
    staleTime: Infinity,
  });
}
