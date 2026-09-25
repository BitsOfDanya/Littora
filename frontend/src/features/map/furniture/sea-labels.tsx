"use client";

import { useCallback, useRef } from "react";
import { findAoi } from "@/config/aois";
import type { WaterLabel } from "@/domain/aoi";
import { useWorkspaceStore } from "@/state/workspace-store";
import { cn } from "@/ui/cn";
import { useMainMap } from "../use-main-map";
import { useGroundInk } from "../use-map-palette";
import type { Edges } from "./use-furniture-layout";
import { useMapRedraw } from "./use-map-redraw";
import { viewportProjector } from "./viewport-projector";

const MAX_LABELS = 3;
const NO_LABELS: readonly WaterLabel[] = [];

function haloShadow(halo: string): string {
  return `0 0 1.4px ${halo}, 0 0 1.4px ${halo}, 0 0 3px ${halo}`;
}

function fitsInside(
  center: { x: number; y: number },
  element: HTMLElement,
  width: number,
  height: number,
  interior: Edges,
): boolean {
  const halfWidth = element.offsetWidth / 2;
  const halfHeight = element.offsetHeight / 2;
  return (
    center.x - halfWidth >= interior.left &&
    center.x + halfWidth <= width - interior.right &&
    center.y - halfHeight >= interior.top &&
    center.y + halfHeight <= height - interior.bottom
  );
}

export function SeaLabels({ interior }: { interior: Edges }) {
  const map = useMainMap();
  const aoiId = useWorkspaceStore((state) => state.aoiId);
  const labels = findAoi(aoiId)?.waterLabels ?? NO_LABELS;
  const ink = useGroundInk();
  const rootRef = useRef<HTMLDivElement>(null);
  const labelRefs = useRef<(HTMLSpanElement | null)[]>([]);
  const { top, right, bottom, left } = interior;

  const draw = useCallback(() => {
    const root = rootRef.current;
    if (!map || !root) return;
    const projector = viewportProjector(map, root);
    const zoom = map.getZoom();
    const edges = { top, right, bottom, left };
    labels.slice(0, MAX_LABELS).forEach((label, index) => {
      const element = labelRefs.current[index];
      if (!element) return;
      const center = projector.project(label.position[0], label.position[1]);
      const shown =
        zoom >= (label.minZoom ?? 0) &&
        fitsInside(center, element, projector.width, projector.height, edges);
      element.style.transform = `translate(${Math.round(center.x - element.offsetWidth / 2)}px, ${Math.round(center.y - element.offsetHeight / 2)}px)`;
      element.style.visibility = shown ? "visible" : "hidden";
    });
  }, [map, labels, top, right, bottom, left]);

  useMapRedraw(map, rootRef, draw);

  return (
    <div ref={rootRef} aria-hidden className="pointer-events-none absolute inset-0 overflow-hidden">
      {labels.slice(0, MAX_LABELS).map((label, index) => (
        <span
          key={label.name}
          ref={(element) => {
            labelRefs.current[index] = element;
          }}
          className={cn(
            "absolute top-0 left-0 font-serif leading-none tracking-[0.22em] whitespace-nowrap italic",
            label.rank === "major" ? "text-[18px]" : "text-[15px]",
          )}
          style={{ visibility: "hidden", color: ink.water, textShadow: haloShadow(ink.halo) }}
        >
          {label.name}
        </span>
      ))}
    </div>
  );
}
