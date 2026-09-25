"use client";

import { useEffect, useState } from "react";
import { HEALTH_RETRY_MS, useBackendHealth, type BackendHealth } from "./use-backend-health";

export const SLOW_API_MS = 800;

export type ApiState = "checking" | "online" | "slow" | "offline";

export type ApiStatus = {
  state: ApiState;
  health: BackendHealth | undefined;
  lastContactAt: number | null;
  lastCheckAt: number | null;
  retryInSeconds: number | null;
  error: unknown;
};

function stateOf(
  isPending: boolean,
  isError: boolean,
  health: BackendHealth | undefined,
): ApiState {
  if (isError) return "offline";
  if (isPending || !health) return "checking";
  return health.latencyMs > SLOW_API_MS ? "slow" : "online";
}

function useSecondTicker(enabled: boolean): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!enabled) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [enabled]);
  return now;
}

export function useApiStatus(): ApiStatus {
  const { data, error, isPending, isError, dataUpdatedAt, errorUpdatedAt } = useBackendHealth();
  const state = stateOf(isPending, isError, data);
  const now = useSecondTicker(state === "offline");
  const retryInSeconds =
    state === "offline" && errorUpdatedAt
      ? Math.max(0, Math.ceil((errorUpdatedAt + HEALTH_RETRY_MS - now) / 1000))
      : null;
  const lastCheckAt = Math.max(dataUpdatedAt, errorUpdatedAt) || null;
  return {
    state,
    health: data,
    lastContactAt: dataUpdatedAt || null,
    lastCheckAt,
    retryInSeconds,
    error,
  };
}
