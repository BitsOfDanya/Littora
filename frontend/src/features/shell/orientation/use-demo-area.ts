"use client";

import { useEffect, useRef } from "react";
import { DEMO_AOI, findAoi } from "@/config/aois";
import { fitAoi } from "@/features/map/camera";
import { useMainMap } from "@/features/map/use-main-map";
import { useWorkspaceStore } from "@/state/workspace-store";

export function useDemoArea(): void {
  const demoFixtures = useWorkspaceStore((state) => state.demoFixtures);
  const setAoi = useWorkspaceStore((state) => state.setAoi);
  const map = useMainMap();
  const previousRef = useRef(demoFixtures);

  useEffect(() => {
    const switchedOn = demoFixtures && !previousRef.current;
    previousRef.current = demoFixtures;
    if (!switchedOn || useWorkspaceStore.getState().aoiId === DEMO_AOI) return;
    setAoi(DEMO_AOI);
    const area = findAoi(DEMO_AOI);
    if (map && area) fitAoi(map, area);
  }, [demoFixtures, map, setAoi]);
}
