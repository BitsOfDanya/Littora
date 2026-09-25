"use client";

import { useQuery } from "@tanstack/react-query";
import { getHealth, type Health } from "@/lib/api/system";
import { queryKeys } from "@/lib/query/query-keys";

const HEALTH_POLL_MS = 15_000;
export const HEALTH_RETRY_MS = 10_000;

export type BackendHealth = Health & { latencyMs: number };

async function measureHealth({ signal }: { signal: AbortSignal }): Promise<BackendHealth> {
  const startedAt = performance.now();
  const health = await getHealth(signal);
  return { ...health, latencyMs: Math.round(performance.now() - startedAt) };
}

export function useBackendHealth() {
  return useQuery({
    queryKey: queryKeys.system.health,
    queryFn: measureHealth,
    refetchInterval: (query) => (query.state.status === "error" ? HEALTH_RETRY_MS : HEALTH_POLL_MS),
    refetchIntervalInBackground: false,
    refetchOnWindowFocus: true,
    retry: false,
    staleTime: 0,
  });
}
