"use client";

import { type ReactNode, useCallback } from "react";
import type { LayerDefinition } from "@/config/layers";
import { useGround } from "@/features/map/use-map-palette";
import { useMapLayersStore, useParticlesPaused } from "@/state/map-layers-store";
import { Button } from "@/ui/button";
import { IconPause, IconPlay } from "@/ui/icons";
import { Kbd } from "@/ui/kbd";
import { AoiSwatch } from "./legend-swatches";
import { useCurrentScene } from "./use-current-scene";

export type LayerRowExtras = {
  label?: string;
  description?: ReactNode;
  trailing?: ReactNode;
  forceLegend?: boolean;
};

export function ParticlesPauseButton() {
  const paused = useParticlesPaused();
  const toggle = useMapLayersStore((state) => state.toggleParticlesPaused);
  return (
    <Button
      size="sm"
      aria-pressed={paused}
      title={paused ? "Запустить частицы течений · M" : "Остановить частицы течений · M"}
      icon={paused ? <IconPlay size={12} /> : <IconPause size={12} />}
      onClick={toggle}
    >
      {paused ? "Пуск" : "Пауза"}
      <Kbd className="h-4 min-w-4 text-[11px]">M</Kbd>
    </Button>
  );
}

export function useRowExtras(): (layer: LayerDefinition) => LayerRowExtras {
  const ground = useGround();
  const tile = useCurrentScene()?.scene.mgrsTile;

  return useCallback(
    (layer: LayerDefinition): LayerRowExtras => {
      switch (layer.id) {
        case "scene-footprint":
          return tile ? { label: `${layer.label} T${tile}` } : {};
        case "hotspots":
          return { description: "ячейки 1 км при отдалении (z < 9)" };
        case "aoi-boundary":
          return { trailing: <AoiSwatch ground={ground} /> };
        case "graticule":
          return { trailing: <Kbd>G</Kbd> };
        case "particles":
          return { trailing: <ParticlesPauseButton /> };
        case "change-delta":
          return { forceLegend: true };
        default:
          return {};
      }
    },
    [ground, tile],
  );
}
