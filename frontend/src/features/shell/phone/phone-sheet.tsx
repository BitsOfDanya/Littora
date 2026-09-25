"use client";

import { type RefObject, useEffect, useRef, useState } from "react";
import type { WorkspaceModeId } from "@/config/modes";
import { Cartouche } from "@/features/cartouche/cartouche";
import { useOverlayRectsStore } from "@/features/map/overlay-rects";
import { useShellUiStore } from "@/state/shell-ui-store";
import { cn } from "@/ui/cn";
import { useEscapeLayer } from "../keyboard/escape-stack";
import { usePrefersReducedMotion } from "../layout/use-environment";
import { useQueue } from "../queue/use-queue";
import { useRegionOccupied, useRegionTarget } from "../shell-slots";
import { detentHeights, nextDetentOnTap, stepDetent } from "./sheet-detents";
import {
  AlarmRow,
  InspectorSummary,
  LayersSummary,
  PANEL_TITLE,
  SheetGrip,
  SheetStatusLine,
  ViewSwitch,
} from "./sheet-parts";
import { useSheetDrag } from "./use-sheet-drag";

function useAvailableHeight(sheetRef: RefObject<HTMLElement | null>): number {
  const [height, setHeight] = useState(0);
  useEffect(() => {
    const parent = sheetRef.current?.parentElement;
    if (!parent) return;
    const observer = new ResizeObserver(([entry]) =>
      setHeight(Math.round(entry.contentRect.height)),
    );
    observer.observe(parent);
    return () => observer.disconnect();
  }, [sheetRef]);
  return height;
}

function useSheetView(inspectorOccupied: boolean) {
  const showSheet = useShellUiStore((state) => state.showSheet);
  const wasOccupiedRef = useRef(inspectorOccupied);

  useEffect(() => {
    const was = wasOccupiedRef.current;
    wasOccupiedRef.current = inspectorOccupied;
    if (inspectorOccupied && !was) showSheet("inspector");
    if (!inspectorOccupied && was) showSheet("layers", "closed");
  }, [inspectorOccupied, showSheet]);
}

export function PhoneSheet({ mode }: { mode: WorkspaceModeId }) {
  const view = useShellUiStore((state) => state.sheetView);
  const detent = useShellUiStore((state) => state.sheetDetent);
  const setDetent = useShellUiStore((state) => state.setSheetDetent);
  const updateDetent = useShellUiStore((state) => state.updateSheetDetent);
  const inspectorOccupied = useRegionOccupied("inspector");
  const inspectorTarget = useRegionTarget("inspector");
  const setRect = useOverlayRectsStore((state) => state.setRect);
  const sheetRef = useRef<HTMLElement>(null);
  const reducedMotion = usePrefersReducedMotion();
  const queue = useQueue();
  const alarm = queue.rows.find((row) => row.state === "new" && row.severity === "alarm");
  const available = useAvailableHeight(sheetRef);
  const heights = detentHeights(available, alarm !== undefined);
  const settledHeight = heights[detent];
  const drag = useSheetDrag(settledHeight, heights, setDetent);
  const height = drag.liveHeight ?? settledHeight;
  const activeView = view === "inspector" && inspectorOccupied ? "inspector" : "layers";

  useSheetView(inspectorOccupied);
  useEscapeLayer(activeView === "layers" && detent !== "closed", () => setDetent("closed"));

  useEffect(() => {
    if (available > 0) setRect("phone-sheet", { edge: "bottom", size: settledHeight });
  }, [available, settledHeight, setRect]);

  useEffect(() => () => setRect("phone-sheet", null), [setRect]);

  return (
    <section
      ref={sheetRef}
      aria-label={activeView === "inspector" ? PANEL_TITLE[mode] : "Слои и объекты"}
      className="pointer-events-auto absolute inset-x-0 bottom-0 z-[4] flex flex-col overflow-hidden rounded-t-[8px] border-t border-line-control bg-surface-panel shadow-popover"
      style={{
        height,
        transition:
          drag.liveHeight !== null || reducedMotion ? "none" : "height var(--t-4) var(--e-std)",
      }}
    >
      <div className="relative shrink-0 border-b border-line-hairline">
        <SheetGrip
          detent={detent}
          drag={drag}
          onCycle={() => updateDetent(nextDetentOnTap)}
          onStep={(direction) => updateDetent((current) => stepDetent(current, direction))}
        >
          {activeView === "inspector" ? <InspectorSummary mode={mode} /> : <LayersSummary />}
        </SheetGrip>
        <ViewSwitch view={activeView} canShowInspector={inspectorOccupied} mode={mode} />
      </div>
      {alarm ? <AlarmRow row={alarm} /> : null}
      <div className={cn("min-h-0 flex-1 flex-col", activeView === "layers" ? "flex" : "hidden")}>
        <div className="min-h-0 flex-1 overflow-y-auto">
          <Cartouche variant="sheet" />
        </div>
        <SheetStatusLine />
      </div>
      <div
        ref={inspectorTarget}
        className={cn(
          "min-h-0 flex-1 overflow-y-auto overscroll-contain",
          activeView === "inspector" ? "block" : "hidden",
        )}
      />
    </section>
  );
}
