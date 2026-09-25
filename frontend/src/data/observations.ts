"use client";

import { useQuery } from "@tanstack/react-query";
import { findAoi } from "@/config/aois";
import { type FieldObservation, getObservations, type ObservationQuery } from "@/lib/api/case";
import { queryKeys } from "@/lib/query/query-keys";
import { useWorkspaceStore } from "@/state/workspace-store";

const NO_OBSERVATIONS: readonly FieldObservation[] = [];
const OBSERVATIONS_STALE_MS = 30 * 60_000;

export function useFieldObservations() {
  const aoi = findAoi(useWorkspaceStore((state) => state.aoiId));
  const query: ObservationQuery = { bbox: aoi?.bbox, decision: "accepted" };
  const result = useQuery({
    queryKey: queryKeys.case.observations(query),
    queryFn: ({ signal }) => getObservations(query, signal),
    enabled: aoi !== undefined,
    staleTime: OBSERVATIONS_STALE_MS,
  });
  return {
    observations: result.data ?? NO_OBSERVATIONS,
    isPending: result.isPending,
    isError: result.isError,
  };
}
