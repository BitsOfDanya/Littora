"use client";

import { useCallback } from "react";
import type { LayerDefinition } from "@/config/layers";
import { useCandidates } from "@/data/candidates";
import { useApiMeta } from "@/features/system/use-capabilities";
import type { CapabilityKey, Meta } from "@/lib/api/system";

export type LayerTruth = "real" | "demo" | "planned";

export type LayerTruthResolver = (layer: LayerDefinition) => LayerTruth;

function isAvailable(meta: Meta | undefined, key: CapabilityKey): boolean {
  return (
    meta?.capabilities.some(
      (capability) => capability.key === key && capability.status === "available",
    ) ?? false
  );
}

export function useDemoActive(): boolean {
  return useCandidates().origin === "demo";
}

export function useDemoFixturesOff(): boolean {
  return useCandidates().origin === "none";
}

export function useLayerTruth(): LayerTruthResolver {
  const { data: meta } = useApiMeta();
  const demoActive = useDemoActive();
  return useCallback(
    (layer: LayerDefinition): LayerTruth => {
      if (!layer.capability || isAvailable(meta, layer.capability)) return "real";
      return layer.hasDemo && demoActive ? "demo" : "planned";
    },
    [meta, demoActive],
  );
}
