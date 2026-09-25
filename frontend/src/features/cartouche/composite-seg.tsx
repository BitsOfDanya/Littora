"use client";

import type { CompositeLayerId, LayerDefinition } from "@/config/layers";
import type { Sentinel2BandId } from "@/domain/sentinel2";
import { cn } from "@/ui/cn";
import { type BandTint, SpectralRibbon } from "@/ui/spectral-ribbon";
import type { LayerTruthResolver } from "./use-layer-truth";

type CompositeSpec = { title: string; lit: Partial<Record<Sentinel2BandId, BandTint>> };

const COMPOSITES: Record<CompositeLayerId, CompositeSpec> = {
  "scene-true-color": {
    title: "Естественные цвета · B04 B03 B02",
    lit: { B04: "r", B03: "g", B02: "b" },
  },
  "scene-false-color": {
    title: "Ложные цвета · B08 B04 B03",
    lit: { B08: "r", B04: "g", B03: "b" },
  },
  "scene-fdi": {
    title: "FDI · индекс плавающего мусора · B06 B08 B11",
    lit: { B06: "index", B08: "index", B11: "index" },
  },
  "scene-ndvi": { title: "NDVI · водоросли · B04 B08", lit: { B04: "index", B08: "index" } },
};

const PLANNED_REASON = "Нужен каталог сцен · scene_catalog: planned";

type CompositeSegProps = {
  layers: readonly LayerDefinition[];
  truthOf: LayerTruthResolver;
  value: CompositeLayerId | null;
  onChange: (value: CompositeLayerId) => void;
  touch?: boolean;
};

function isComposite(id: string): id is CompositeLayerId {
  return id in COMPOSITES;
}

export function CompositeSeg({ layers, truthOf, value, onChange, touch }: CompositeSegProps) {
  return (
    <div role="radiogroup" aria-label="Композит снимка даты" className="grid grid-cols-4 gap-1">
      {layers.map((layer) => {
        if (!isComposite(layer.id)) return null;
        const spec = COMPOSITES[layer.id];
        const planned = truthOf(layer) === "planned";
        const selected = !planned && value === layer.id;
        const compositeId = layer.id;
        return (
          <button
            key={layer.id}
            type="button"
            role="radio"
            aria-checked={selected}
            aria-disabled={planned || undefined}
            aria-label={
              planned
                ? `${layer.label}: ${spec.title}. ${PLANNED_REASON}`
                : `${layer.label}: ${spec.title}`
            }
            title={planned ? `${spec.title}\n${PLANNED_REASON}` : spec.title}
            onClick={() => {
              if (!planned) onChange(compositeId);
            }}
            className={cn(
              "flex flex-col items-center justify-center gap-1 rounded-[var(--radius-ctl)] border text-[12px] leading-none transition-colors duration-[var(--t-2)]",
              touch ? "h-12" : "h-11",
              planned
                ? "cursor-not-allowed border-dashed border-line-control text-text-tertiary"
                : "border-line-control bg-surface-raised text-text-secondary hover:border-line-strong hover:text-text-primary",
              selected &&
                "font-semibold text-text-primary shadow-[inset_0_0_0_1px_var(--text-primary)]",
            )}
          >
            <span>{layer.label}</span>
            <SpectralRibbon
              lit={spec.lit}
              showTitles={false}
              className={cn(planned && "opacity-70")}
            />
          </button>
        );
      })}
    </div>
  );
}
