"use client";

import { useEffect, useRef } from "react";

type EscapeLayer = { token: symbol; close: () => void };

const layers: EscapeLayer[] = [];

export function useEscapeLayer(active: boolean, close: () => void): void {
  const closeRef = useRef(close);

  useEffect(() => {
    closeRef.current = close;
  });

  useEffect(() => {
    if (!active) return;
    const layer: EscapeLayer = { token: Symbol("escape-layer"), close: () => closeRef.current() };
    layers.push(layer);
    return () => {
      const index = layers.findIndex((entry) => entry.token === layer.token);
      if (index !== -1) layers.splice(index, 1);
    };
  }, [active]);
}

export function closeTopEscapeLayer(): boolean {
  const top = layers.at(-1);
  if (!top) return false;
  top.close();
  return true;
}

export function hasEscapeLayers(): boolean {
  return layers.length > 0;
}
