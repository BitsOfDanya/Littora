"use client";

import type { ReactNode } from "react";
import {
  LAYER_GROUP_LABELS,
  type LayerDefinition,
  type LayerGroupId,
  layersInGroup,
  type MapModeId,
} from "@/config/layers";
import { useGround } from "@/features/map/use-map-palette";
import { useMapLayersStore } from "@/state/map-layers-store";
import { GroupSection } from "./group-section";
import { hasLegend, LayerLegend, LegendNote } from "./layer-legend";
import { LayerRow, type RowDensity } from "./layer-row";
import { useRowExtras } from "./layer-row-extras";
import type { LayerTruthResolver } from "./use-layer-truth";

const DEMO_SOURCE: Partial<Record<LayerGroupId, string>> = {
  results: "фикстура demo/candidates · не результат модели",
  conditions: "фикстура demo/scenes · не результат модели",
  survey: "фикстура demo/survey · не результат модели",
};

type LayerRowsGroupProps = {
  mode: MapModeId;
  group: LayerGroupId;
  truthOf: LayerTruthResolver;
  showAll: boolean;
  density: RowDensity;
  defaultOpen?: boolean;
  plannedNote?: ReactNode;
  showPlanned?: boolean;
  demo?: boolean;
  lead?: ReactNode;
  footnote?: ReactNode;
};

function visibleCount(
  layers: readonly LayerDefinition[],
  visible: Readonly<Partial<Record<string, boolean>>>,
  truthOf: LayerTruthResolver,
) {
  return layers.filter((layer) => truthOf(layer) !== "planned" && visible[layer.id]).length;
}

export function LayerRowsGroup({
  mode,
  group,
  truthOf,
  showAll,
  density,
  defaultOpen,
  plannedNote,
  showPlanned,
  demo,
  lead,
  footnote,
}: LayerRowsGroupProps) {
  const ground = useGround();
  const visible = useMapLayersStore((state) => state.visible);
  const extrasFor = useRowExtras();
  const layers = layersInGroup(mode, group);
  const available = layers.filter((layer) => truthOf(layer) !== "planned");
  const rows = showAll || showPlanned ? layers : available;
  const allDemo = available.length > 0 && available.every((layer) => truthOf(layer) === "demo");
  const collapsedToNote = !showAll && available.length === 0 && plannedNote;
  const groupFootnote = footnote ?? (allDemo ? DEMO_SOURCE[group] : undefined);

  if (layers.length === 0 || (rows.length === 0 && !collapsedToNote && !lead)) return null;

  return (
    <GroupSection
      mode={mode}
      id={group}
      title={LAYER_GROUP_LABELS[group]}
      demo={demo || allDemo}
      defaultOpen={defaultOpen}
      density={density}
      summary={`${visibleCount(layers, visible, truthOf)} вкл`}
    >
      {collapsedToNote ? (
        plannedNote
      ) : (
        <>
          {lead}
          {rows.map((layer) => {
            const truth = truthOf(layer);
            return (
              <LayerRow
                key={layer.id}
                layer={layer}
                truth={truth}
                density={density}
                showDemoTag={!allDemo}
                legend={
                  hasLegend(layer.legend) ? (
                    <LayerLegend kind={layer.legend} ground={ground} />
                  ) : undefined
                }
                source={!allDemo && truth === "demo" ? DEMO_SOURCE[group] : undefined}
                {...extrasFor(layer)}
              />
            );
          })}
          {groupFootnote ? (
            <div className="pt-1">
              <LegendNote tone="source">{groupFootnote}</LegendNote>
            </div>
          ) : null}
        </>
      )}
    </GroupSection>
  );
}
