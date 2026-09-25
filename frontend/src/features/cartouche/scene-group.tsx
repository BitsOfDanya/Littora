"use client";

import { layersInGroup, type MapModeId } from "@/config/layers";
import { useMapLayersStore } from "@/state/map-layers-store";
import { BASEMAP_SHORT } from "./basemap-group";
import { CompositeSeg } from "./composite-seg";
import { GroupSection } from "./group-section";
import { LegendNote } from "./layer-legend";
import type { RowDensity } from "./layer-row";
import { useCurrentScene } from "./use-current-scene";
import type { LayerTruthResolver } from "./use-layer-truth";

export function dayMonth(iso: string): string {
  return `${iso.slice(8, 10)}.${iso.slice(5, 7)}`;
}

export function SceneGroup({
  mode,
  truthOf,
  density,
}: {
  mode: MapModeId;
  truthOf: LayerTruthResolver;
  density: RowDensity;
}) {
  const current = useCurrentScene();
  const basemapId = useMapLayersStore((state) => state.basemapId);
  const composite = useMapLayersStore((state) => state.composite);
  const setComposite = useMapLayersStore((state) => state.setComposite);
  const layers = layersInGroup(mode, "scene");
  const allPlanned = layers.every((layer) => truthOf(layer) === "planned");

  if (layers.length === 0) return null;

  return (
    <GroupSection
      mode={mode}
      id="scene"
      title={current ? `Снимок даты · ${dayMonth(current.scene.acquiredAt)}` : "Снимок даты"}
      demo={current?.isDemo}
      density={density}
      summary={allPlanned ? "план" : undefined}
    >
      <div className="flex flex-col gap-1.5 pt-1">
        <CompositeSeg
          layers={layers}
          truthOf={truthOf}
          value={composite}
          onChange={setComposite}
          touch={density === "touch"}
        />
        {allPlanned ? (
          <LegendNote tone="source">
            {current ? "Сцена не подключена" : "Сцена не выбрана"} — показана подложка (
            {BASEMAP_SHORT[basemapId]})
          </LegendNote>
        ) : null}
      </div>
    </GroupSection>
  );
}
