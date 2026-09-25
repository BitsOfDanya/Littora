"use client";

import type { ReactNode } from "react";
import { findLayer, type LayerId, type MapModeId } from "@/config/layers";
import { rampFor } from "@/features/map/ramps";
import { useGround } from "@/features/map/use-map-palette";
import { useLayerVisible } from "@/state/map-layers-store";
import { PlannedTag } from "@/ui/planned";
import { coverageRangeLabel, MiniRamp } from "./legend-ramp";
import { EnvelopeSwatch, TargetSwatch } from "./legend-swatches";
import { useLayerTruth } from "./use-layer-truth";

const PRIMARY_LAYER: Record<MapModeId, LayerId> = {
  monitor: "coverage",
  timeline: "coverage",
  forecast: "forecast-envelopes",
  survey: "survey-targets",
};

function KeyCaption({ children }: { children: string }) {
  return (
    <span className="font-mono text-[10.5px] leading-3 font-medium whitespace-nowrap text-text-tertiary">
      {children}
    </span>
  );
}

function KeyStack({ label, glyph, caption }: { label: string; glyph: ReactNode; caption: string }) {
  return (
    <span role="img" aria-label={label} className="flex flex-col items-center gap-0.5">
      {glyph}
      <KeyCaption>{caption}</KeyCaption>
    </span>
  );
}

function PrimaryKey({ layerId }: { layerId: LayerId }) {
  const ground = useGround();
  if (layerId === "coverage") {
    const ramp = rampFor("coverage", ground);
    const range = coverageRangeLabel(ramp);
    return (
      <KeyStack
        label={`Доля покрытия пикселя: ${range}`}
        glyph={<MiniRamp ramp={ramp} />}
        caption={range}
      />
    );
  }
  if (layerId === "forecast-envelopes") {
    return (
      <KeyStack
        label={"Облако вероятности: +6…+72\u202Fч"}
        glyph={<EnvelopeSwatch ground={ground} alpha={0.18} />}
        caption={"+6…+72\u202Fч"}
      />
    );
  }
  return (
    <KeyStack
      label="Цели обследования по очереди"
      glyph={<TargetSwatch ground={ground} />}
      caption="цели"
    />
  );
}

export function MiniKey({ mode }: { mode: MapModeId }) {
  const layerId = PRIMARY_LAYER[mode];
  const layer = findLayer(layerId);
  const truthOf = useLayerTruth();
  const visible = useLayerVisible(layerId);
  if (!layer) return null;
  if (truthOf(layer) === "planned")
    return layer.capability ? <PlannedTag capability={layer.capability} /> : null;
  return visible ? <PrimaryKey layerId={layerId} /> : null;
}
