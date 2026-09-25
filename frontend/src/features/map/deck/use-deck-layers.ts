"use client";

import type { Layer } from "@deck.gl/core";
import { useEffect } from "react";
import { useDeckLayerStore } from "../state/deck-layer-store";

export function useDeckLayers(owner: string, layers: readonly Layer[]): void {
  const setGroup = useDeckLayerStore((state) => state.setGroup);
  const removeGroup = useDeckLayerStore((state) => state.removeGroup);

  useEffect(() => {
    setGroup(owner, layers);
  }, [owner, layers, setGroup]);

  useEffect(() => () => removeGroup(owner), [owner, removeGroup]);
}
