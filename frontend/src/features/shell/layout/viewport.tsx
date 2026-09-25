"use client";

import type { RefObject } from "react";
import type { WorkspaceModeId } from "@/config/modes";
import { Cartouche } from "@/features/cartouche/cartouche";
import { MapFurniture } from "@/features/map/furniture/map-furniture";
import { MapControls } from "@/features/map/map-controls";
import { useShellUiStore } from "@/state/shell-ui-store";
import { PhoneSheet } from "../phone/phone-sheet";
import { useRegionTarget } from "../shell-slots";
import styles from "../workspace-shell.module.css";
import type { ShellLayout } from "./use-environment";

type ViewportProps = {
  viewportRef: RefObject<HTMLDivElement | null>;
  mode: WorkspaceModeId | undefined;
  layout: ShellLayout;
};

export function Viewport({ viewportRef, mode, layout }: ViewportProps) {
  const overlayRef = useRegionTarget("map-overlay");
  const showSheet = useShellUiStore((state) => state.showSheet);
  const openLayersSheet = () => showSheet("layers", "half");
  const isChartMode = mode !== undefined && mode !== "models";
  const isPhone = layout === "phone";

  return (
    <div ref={viewportRef} className={styles.viewport}>
      {isChartMode ? <MapFurniture /> : null}
      <div ref={overlayRef} className="contents" />
      {isChartMode && !isPhone ? <Cartouche /> : null}
      {isChartMode ? (
        <div className={styles.tools}>
          <MapControls onOpenLayers={isPhone ? openLayersSheet : undefined} />
        </div>
      ) : null}
      {isChartMode && isPhone ? <PhoneSheet mode={mode} /> : null}
    </div>
  );
}
