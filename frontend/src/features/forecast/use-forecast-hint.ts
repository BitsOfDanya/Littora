"use client";

import { useEffect } from "react";
import { useDriftState } from "@/data/forecast";
import { useStatusHintStore } from "@/features/shell/status-hint-store";
import { useWorkspaceStore } from "@/state/workspace-store";

export const EMPTY_FORECAST_HINT = "Выберите пятно, чтобы построить прогноз";

export function useForecastEmptyHint(active: boolean): void {
  const hint = useStatusHintStore((state) => state.hint);
  const setHint = useStatusHintStore((state) => state.setHint);

  useEffect(() => {
    if (active && hint === null) setHint(EMPTY_FORECAST_HINT);
    if (!active && hint === EMPTY_FORECAST_HINT) setHint(null);
  }, [active, hint, setHint]);

  useEffect(
    () => () => {
      const { hint: current, setHint: reset } = useStatusHintStore.getState();
      if (current === EMPTY_FORECAST_HINT) reset(null);
    },
    [],
  );
}

export function useForecastPickHint(): boolean {
  const hasSelection = useWorkspaceStore((state) => state.selectedCandidateId !== null);
  const drift = useDriftState().status;
  return !hasSelection && (drift === "demo" || drift === "ready");
}
