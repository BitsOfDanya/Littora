"use client";

import { useMemo } from "react";
import type { LngLat } from "@/domain/geo";
import { boundsOf } from "@/features/forecast/drift-math";
import { useFrameOnce } from "@/features/map/use-frame-once";
import type { SurveyView } from "./use-survey-view";

const FIT_MAX_ZOOM = 12;
const CRAMPED_SHARE = 0.5;

function framingPoints(view: SurveyView): LngLat[] {
  const points: LngLat[] = [...view.route.path];
  for (const target of view.plan.targets) {
    points.push(target.observedPosition);
    const drifted = view.drift.get(target.id)?.position;
    if (drifted) points.push(drifted);
  }
  if (view.plan.port) points.push(view.plan.port.position);
  return points;
}

export function useSurveyCamera(view: SurveyView | null): void {
  const live = view && !view.isDemo ? view : null;
  const bbox = useMemo(() => {
    const points = live ? framingPoints(live) : [];
    return points.length ? boundsOf(points) : null;
  }, [live]);
  useFrameOnce(live?.plan.id ?? null, bbox, {
    maxZoom: FIT_MAX_ZOOM,
    crampedShare: CRAMPED_SHARE,
    tighten: true,
  });
}
