"use client";

import { useMemo } from "react";
import { useFieldObservations } from "@/data/observations";
import type { LngLat } from "@/domain/geo";
import { useSelectedScene } from "@/features/time-rail/use-selected-scene";
import type { FieldObservation } from "@/lib/api/case";
import { useAnalysisStore } from "@/state/analysis-store";
import { dayOffset } from "./format";
import { useCurrentAnalysis } from "./use-analysis";

export type TimedObservation = {
  feature: FieldObservation;
  point: LngLat;
  deltaDays: number | null;
  inWindow: boolean;
};

export function observationPoint(feature: FieldObservation): LngLat {
  const geometry = feature.geometry;
  if (geometry.type === "Point") return geometry.coordinates;
  const first = geometry.coordinates[0];
  const last = geometry.coordinates.at(-1) ?? first;
  return [(first[0] + last[0]) / 2, (first[1] + last[1]) / 2];
}

function timed(
  feature: FieldObservation,
  referenceDay: string | null,
  windowDays: number,
): TimedObservation {
  const date = feature.properties.date;
  const deltaDays = referenceDay && date ? dayOffset(referenceDay, date) : null;
  return {
    feature,
    point: observationPoint(feature),
    deltaDays,
    inWindow: deltaDays !== null && Math.abs(deltaDays) <= windowDays,
  };
}

export function useObservationsView() {
  const analysis = useCurrentAnalysis().data ?? null;
  const field = useFieldObservations();
  const { scene, isDemo } = useSelectedScene();
  const draftWindow = useAnalysisStore((state) => state.windowDays);
  const dates = useAnalysisStore((state) => state.observationDates);
  const referenceDay =
    analysis?.scene?.acquired_at ?? analysis?.request.date ?? (isDemo ? null : scene?.acquiredAt);
  const reference = referenceDay ? referenceDay.slice(0, 10) : null;
  const windowDays = analysis?.request.window_days ?? draftWindow;

  const mapped = useMemo(
    () => field.observations.map((feature) => timed(feature, reference, windowDays)),
    [field.observations, reference, windowDays],
  );
  const listed = useMemo(
    () =>
      (analysis ? analysis.observations : field.observations).map((feature) =>
        timed(feature, reference, windowDays),
      ),
    [analysis, field.observations, reference, windowDays],
  );
  const windowOnly = dates === "window" && reference !== null;
  const onMap = useMemo(
    () => (windowOnly ? mapped.filter((item) => item.inWindow) : mapped),
    [mapped, windowOnly],
  );
  const shown = useMemo(
    () => (windowOnly ? listed.filter((item) => item.inWindow) : listed),
    [listed, windowOnly],
  );

  return {
    onMap,
    mapTotal: mapped.length,
    mapInWindow: mapped.filter((item) => item.inWindow).length,
    listed: shown,
    total: listed.length,
    reference,
    windowDays,
    dates,
    isPending: field.isPending,
    isError: field.isError,
  };
}
