"use client";

import { useEffect, useRef } from "react";
import type { DriftForecastDetail } from "@/data/forecast";
import type { LngLat } from "@/domain/geo";
import { fitTo, isDefaultFitDone, isInVisibleField, targetPadding } from "@/features/map/camera";
import { useMainMap } from "@/features/map/use-main-map";
import { boundsOf } from "./drift-math";

const LAYOUT_SETTLE_MS = 300;
const RETRY_MS = 200;
const MAX_WAIT_MS = 4_000;
const FIT_MS = 600;
const FIT_MAX_ZOOM = 11.5;

function framingPoints(forecast: DriftForecastDetail): LngLat[] {
  return [
    ...forecast.medianPath,
    ...forecast.hindcastPath,
    ...forecast.envelopes.flatMap(
      (envelope) => envelope.polygon.coordinates[0] as unknown as LngLat[],
    ),
    ...forecast.beaching.filter((risk) => risk.severity !== "info").flatMap((risk) => risk.path),
  ];
}

export function useForecastCamera(forecast: DriftForecastDetail | null): void {
  const map = useMainMap();
  const framedRef = useRef<string | null>(null);

  useEffect(() => {
    if (!forecast) {
      framedRef.current = null;
      return;
    }
    if (!map || framedRef.current === forecast.candidateId) return;
    framedRef.current = forecast.candidateId;
    let userMoved = false;
    let timer = 0;
    let waited = 0;
    const onMoveStart = (event: { originalEvent?: unknown }) => {
      if (event.originalEvent) userMoved = true;
    };
    const frame = () => {
      if (userMoved) return;
      if ((!isDefaultFitDone() || map.isMoving()) && waited < MAX_WAIT_MS) {
        waited += RETRY_MS;
        timer = window.setTimeout(frame, RETRY_MS);
        return;
      }
      map.off("movestart", onMoveStart);
      const [west, south, east, north] = boundsOf(framingPoints(forecast));
      const padding = targetPadding(map);
      const corners: LngLat[] = [
        [west, south],
        [west, north],
        [east, south],
        [east, north],
      ];
      if (corners.every((corner) => isInVisibleField(map, corner, padding))) return;
      fitTo(map, [west, south, east, north], {
        durationMs: FIT_MS,
        maxZoom: FIT_MAX_ZOOM,
        padding,
      });
    };
    map.on("movestart", onMoveStart);
    timer = window.setTimeout(frame, LAYOUT_SETTLE_MS);
    return () => {
      window.clearTimeout(timer);
      map.off("movestart", onMoveStart);
    };
  }, [map, forecast]);
}
