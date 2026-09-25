"use client";

import { useEffect } from "react";
import { create } from "zustand";
import type { QueueEvent } from "@/data/events";
import { type ApiState, useApiStatus } from "./use-api-status";

type SystemEventsStore = {
  events: readonly QueueEvent[];
  apiLost: boolean;
  markApiLost: (at: Date) => void;
  markApiRestored: (at: Date) => void;
};

function apiEvent(kind: "api_lost" | "api_restored", at: Date): QueueEvent {
  const lost = kind === "api_lost";
  return {
    id: `SYS-${kind}-${at.getTime()}`,
    kind,
    severity: lost ? "alarm" : "info",
    occurredAt: at.toISOString(),
    stamp: "time",
    title: lost ? "Нет связи с API" : "Связь с API восстановлена",
    candidateId: null,
    acknowledged: null,
  };
}

export const useSystemEventsStore = create<SystemEventsStore>()((set) => ({
  events: [],
  apiLost: false,
  markApiLost: (at) =>
    set((state) =>
      state.apiLost
        ? state
        : { apiLost: true, events: [...state.events, apiEvent("api_lost", at)] },
    ),
  markApiRestored: (at) =>
    set((state) =>
      state.apiLost
        ? { apiLost: false, events: [...state.events, apiEvent("api_restored", at)] }
        : state,
    ),
}));

const isReachable = (state: ApiState) => state === "online" || state === "slow";

export function useSystemEventsWatcher(): void {
  const { state } = useApiStatus();
  const markApiLost = useSystemEventsStore((store) => store.markApiLost);
  const markApiRestored = useSystemEventsStore((store) => store.markApiRestored);

  useEffect(() => {
    if (state === "offline") markApiLost(new Date());
    else if (isReachable(state)) markApiRestored(new Date());
  }, [state, markApiLost, markApiRestored]);
}
