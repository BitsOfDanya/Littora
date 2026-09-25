"use client";

import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import { createPortal } from "react-dom";

export type ShellRegion = "side" | "inspector" | "rail" | "map-overlay" | "stepper";

type RegionTargets = Partial<Record<ShellRegion, HTMLElement | null>>;
type RegionCounts = Partial<Record<ShellRegion, number>>;

type ShellSlotsContextValue = {
  targets: RegionTargets;
  counts: RegionCounts;
  registerTarget: (region: ShellRegion, element: HTMLElement | null) => void;
  claim: (region: ShellRegion) => () => void;
};

const ShellSlotsContext = createContext<ShellSlotsContextValue | null>(null);

function useShellSlotsContext(): ShellSlotsContextValue {
  const context = useContext(ShellSlotsContext);
  if (!context) throw new Error("Shell slots are used outside of <ShellSlotsProvider>");
  return context;
}

export function ShellSlotsProvider({ children }: { children: ReactNode }) {
  const [targets, setTargets] = useState<RegionTargets>({});
  const [counts, setCounts] = useState<RegionCounts>({});

  const registerTarget = useCallback((region: ShellRegion, element: HTMLElement | null) => {
    setTargets((current) =>
      current[region] === element ? current : { ...current, [region]: element },
    );
  }, []);

  const claim = useCallback((region: ShellRegion) => {
    setCounts((current) => ({ ...current, [region]: (current[region] ?? 0) + 1 }));
    return () =>
      setCounts((current) => ({ ...current, [region]: Math.max(0, (current[region] ?? 1) - 1) }));
  }, []);

  const value = useMemo(
    () => ({ targets, counts, registerTarget, claim }),
    [targets, counts, registerTarget, claim],
  );
  return <ShellSlotsContext.Provider value={value}>{children}</ShellSlotsContext.Provider>;
}

export function useRegionTarget(region: ShellRegion) {
  const { registerTarget } = useShellSlotsContext();
  return useCallback(
    (element: HTMLElement | null) => registerTarget(region, element),
    [region, registerTarget],
  );
}

export function useRegionOccupied(region: ShellRegion): boolean {
  return (useShellSlotsContext().counts[region] ?? 0) > 0;
}

export function ShellSlot({ region, children }: { region: ShellRegion; children: ReactNode }) {
  const { targets, claim } = useShellSlotsContext();
  const target = targets[region];

  useEffect(() => claim(region), [claim, region]);

  return target ? createPortal(children, target) : null;
}
