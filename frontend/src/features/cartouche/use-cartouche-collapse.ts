"use client";

import { useCallback, useEffect } from "react";
import type { MapModeId } from "@/config/layers";
import { useRegionOccupied } from "@/features/shell/shell-slots";
import { useCartoucheStore } from "@/state/cartouche-store";
import { MEDIA, useMediaQuery } from "./use-media-query";

export type CartoucheCollapse = {
  collapsed: boolean;
  toggle: () => void;
  expand: () => void;
};

function useDefaultCollapsed(mode: MapModeId): boolean {
  const laptopUp = useMediaQuery(MEDIA.laptopUp);
  const wideUp = useMediaQuery(MEDIA.wideUp);
  return mode === "monitor" ? !laptopUp : !wideUp;
}

function useAutoCollapseOnInspector(): void {
  const inspectorOpen = useRegionOccupied("inspector");
  const narrow = useMediaQuery(MEDIA.autoCollapse);
  const setAutoCollapsed = useCartoucheStore((state) => state.setAutoCollapsed);

  useEffect(() => {
    setAutoCollapsed(inspectorOpen && narrow);
  }, [inspectorOpen, narrow, setAutoCollapsed]);
}

export function useCartoucheCollapse(mode: MapModeId): CartoucheCollapse {
  const remembered = useCartoucheStore((state) => state.collapsedByMode[mode]);
  const autoCollapsed = useCartoucheStore((state) => state.autoCollapsed);
  const setCollapsed = useCartoucheStore((state) => state.setCollapsed);
  const setAutoCollapsed = useCartoucheStore((state) => state.setAutoCollapsed);
  const defaultCollapsed = useDefaultCollapsed(mode);
  useAutoCollapseOnInspector();

  const collapsed = autoCollapsed || (remembered ?? defaultCollapsed);

  const expand = useCallback(() => {
    setAutoCollapsed(false);
    setCollapsed(mode, false);
  }, [mode, setAutoCollapsed, setCollapsed]);

  const toggle = useCallback(() => {
    if (collapsed) expand();
    else setCollapsed(mode, true);
  }, [collapsed, expand, mode, setCollapsed]);

  return { collapsed, toggle, expand };
}
