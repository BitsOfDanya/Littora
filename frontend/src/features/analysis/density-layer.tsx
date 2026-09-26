"use client";

import type { Layer, PickingInfo } from "@deck.gl/core";
import { PolygonLayer } from "@deck.gl/layers";
import { useMemo } from "react";
import { useDemoActive } from "@/features/cartouche/use-layer-truth";
import { type Anchored, UNDER_LABELS } from "@/features/map/deck/anchors";
import { useDeckLayers } from "@/features/map/deck/use-deck-layers";
import { useStatusHintStore } from "@/features/shell/status-hint-store";
import { formatNumber } from "@/lib/format/numbers";
import { useLayerVisible } from "@/state/map-layers-store";
import { type DensityCell, densityCells } from "./density";
import { useCurrentAnalysis } from "./use-analysis";
import { toRealZones } from "./zones";

function hint(cell: DensityCell): string {
  return `Ячейка 1 км: ${formatNumber(cell.m2PerKm2, 0)} м² материала на км² — ${cell.densityClass.label} · зон ${cell.zones} · оценка по доле покрытия, не концентрация`;
}

export function DensityLayer() {
  const visible = useLayerVisible("density");
  const demoActive = useDemoActive();
  const analysis = useCurrentAnalysis().data ?? null;
  const setHint = useStatusHintStore((state) => state.setHint);
  const cells = useMemo(
    () => (analysis ? densityCells(toRealZones(analysis.detection.zones)) : []),
    [analysis],
  );

  const layers = useMemo(() => {
    const list: Layer[] = [];
    if (!visible || demoActive || !cells.length) return list;
    list.push(
      new PolygonLayer<DensityCell, Anchored>({
        id: "analysis:density",
        ...UNDER_LABELS,
        data: cells,
        getPolygon: (cell) => cell.polygon,
        getFillColor: (cell) => cell.densityClass.color,
        getLineColor: [255, 255, 255, 90],
        getLineWidth: 1,
        lineWidthUnits: "pixels",
        stroked: true,
        filled: true,
        pickable: true,
        onHover: (info: PickingInfo<DensityCell>) =>
          setHint(info.object ? hint(info.object) : null),
      }),
    );
    return list;
  }, [cells, visible, demoActive, setHint]);

  useDeckLayers("density", layers);
  return null;
}
