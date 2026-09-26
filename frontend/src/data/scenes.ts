"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { findAoi } from "@/config/aois";
import { DEMO_PLANNED_PASSES, DEMO_SCENES } from "@/demo/scenes";
import type { Sourced } from "@/domain/data-origin";
import type { SceneSummary } from "@/domain/scene";
import { describeApiError } from "@/lib/api/errors";
import { getScenes, type SceneQuery } from "@/lib/api/scenes";
import { queryKeys } from "@/lib/query/query-keys";
import { useWorkspaceStore } from "@/state/workspace-store";
import { useDemoSourced } from "./use-sourced";

export type { PlannedPass } from "@/demo/scenes";

const RECENT_DAYS = 45;
const DAY_MS = 86_400_000;
const CATALOG_STALE_MS = 10 * 60_000;

export type SceneCatalogState =
  | { status: "demo" }
  | { status: "loading"; query: SceneQuery }
  | { status: "error"; query: SceneQuery; message: string; retry: () => void }
  | { status: "ready"; query: SceneQuery; count: number }
  | { status: "unavailable" };

const isoDay = (time: number) => new Date(time).toISOString().slice(0, 10);

export function sceneQueryFor(aoiId: string, now: number): SceneQuery | null {
  const aoi = findAoi(aoiId);
  if (!aoi) return null;
  const [dateFrom, dateTo] = aoi.survey?.period ??
    aoi.reference?.period ?? [isoDay(now - RECENT_DAYS * DAY_MS), isoDay(now)];
  return { aoiId: aoi.id, bbox: aoi.bbox, dateFrom, dateTo };
}

function useSceneCatalog() {
  const demo = useDemoSourced(DEMO_SCENES);
  const aoiId = useWorkspaceStore((state) => state.aoiId);
  const [mountedAt] = useState(() => Date.now());
  const query = sceneQueryFor(aoiId, mountedAt);
  const result = useQuery({
    queryKey: queryKeys.scenes(query),
    queryFn: ({ signal }) => (query ? getScenes(query, signal) : Promise.resolve([])),
    enabled: demo.origin !== "demo" && query !== null,
    staleTime: CATALOG_STALE_MS,
  });
  return { demo, query, result };
}

export function useScenes(): Sourced<readonly SceneSummary[]> {
  const { demo, result } = useSceneCatalog();
  if (demo.origin === "demo") return demo;
  if (result.data) return { origin: "api", data: result.data };
  return { origin: "none", demo: demo.origin === "none" ? demo.demo : "not-provided" };
}

export function useSceneCatalogState(): SceneCatalogState {
  const { demo, query, result } = useSceneCatalog();
  if (demo.origin === "demo") return { status: "demo" };
  if (!query) return { status: "unavailable" };
  if (result.data) return { status: "ready", query, count: result.data.length };
  if (result.isError)
    return {
      status: "error",
      query,
      message: describeApiError(result.error),
      retry: () => void result.refetch(),
    };
  return { status: "loading", query };
}

export const usePlannedPasses = () => useDemoSourced(DEMO_PLANNED_PASSES);
