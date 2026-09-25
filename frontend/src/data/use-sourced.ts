"use client";

import type { Sourced } from "@/domain/data-origin";
import { DEMO_AOI_ID } from "@/demo/scenario";
import { useWorkspaceStore } from "@/state/workspace-store";

export function useDemoSourced<T>(
  demoData: T,
  options: { aoiScoped: boolean } = { aoiScoped: true },
): Sourced<T> {
  const demoEnabled = useWorkspaceStore((state) => state.demoFixtures);
  const aoiId = useWorkspaceStore((state) => state.aoiId);

  if (!demoEnabled) return { origin: "none", demo: "disabled" };
  if (options.aoiScoped && aoiId !== DEMO_AOI_ID) return { origin: "none", demo: "other-aoi" };
  return { origin: "demo", data: demoData };
}

export function sourcedData<T>(sourced: Sourced<T>, fallback: T): T {
  return sourced.origin === "none" ? fallback : sourced.data;
}
