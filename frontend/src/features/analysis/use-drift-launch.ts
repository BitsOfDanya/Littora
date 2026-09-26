"use client";

import { useRouter } from "next/navigation";
import { useCallback } from "react";
import { WORKSPACE_MODES } from "@/config/modes";
import { useComputeDrift } from "@/data/forecast";
import { modeHref, viewQuery } from "@/features/shell/orientation/modes";
import { useCapability } from "@/features/system/use-capabilities";
import { useAnalysisStore } from "@/state/analysis-store";
import { useWorkspaceStore } from "@/state/workspace-store";

const FORECAST_MODE = WORKSPACE_MODES.find((mode) => mode.id === "forecast") ?? WORKSPACE_MODES[0];

export function useDriftLaunch(): { available: boolean; launch: (analysisId: string) => void } {
  const router = useRouter();
  const compute = useComputeDrift();
  const setAnalysis = useAnalysisStore((state) => state.setAnalysis);
  const aoiId = useWorkspaceStore((state) => state.aoiId);
  const available = useCapability("drift_forecast") === "available";

  const launch = useCallback(
    (analysisId: string) => {
      setAnalysis(analysisId);
      compute(analysisId);
      const params = new URLSearchParams(viewQuery(aoiId, null));
      params.set("analysis", analysisId);
      router.push(modeHref(FORECAST_MODE, params.toString()));
    },
    [aoiId, compute, router, setAnalysis],
  );

  return { available, launch };
}
