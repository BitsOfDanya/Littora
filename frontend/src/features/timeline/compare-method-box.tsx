"use client";

import { useFrameWidth, useIsPhoneWidth } from "@/features/map/furniture/use-frame-width";
import { useMapLayersStore } from "@/state/map-layers-store";
import { Button } from "@/ui/button";
import { IconLens, IconOpacity, IconSwipe } from "@/ui/icons";
import { SeverityGlyph } from "@/ui/indicators";
import { type SegmentOption, Segmented } from "@/ui/segmented";
import { useCompareViewStore } from "./compare-view-store";

export type CompareMethod = "swipe" | "opacity" | "lens";

export const COMPARE_HONESTY_NOTE =
  "Под шторкой — годовые мозаики EOX 2024 и 2025, а не снимки дат A и B: каталог сцен не подключён";

export const METHOD_PLANNED_REASON = "в плане: появится вместе с каталогом сцен";

export const COMPARE_METHODS: readonly SegmentOption<CompareMethod>[] = [
  {
    value: "swipe",
    label: (
      <>
        <IconSwipe size={14} />
        Шторка
      </>
    ),
    title: "Шторка · C",
  },
  {
    value: "opacity",
    label: (
      <>
        <IconOpacity size={14} />
        Прозрачность
      </>
    ),
    disabled: true,
    disabledReason: `Прозрачность — ${METHOD_PLANNED_REASON}`,
  },
  {
    value: "lens",
    label: (
      <>
        <IconLens size={14} />
        Линза
      </>
    ),
    disabled: true,
    disabledReason: `Линза — ${METHOD_PLANNED_REASON}`,
  },
];

const FURNITURE_GAP_PX = 12;

function MosaicStatus() {
  const load = useCompareViewStore((state) => state.mosaicLoad);
  const retry = useCompareViewStore((state) => state.retryMosaic);
  const zoom = useCompareViewStore((state) => state.zoom);
  if (zoom < 6.5)
    return (
      <p className="text-[11px] text-text-tertiary">
        Мельче z 6,5 обе стороны показывают рельеф — приблизьте карту.
      </p>
    );
  if (load === "error")
    return (
      <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[12px] text-state-alarm">
        <SeverityGlyph severity="alarm" size={12} />
        Мозаика 2024: тайлы недоступны
        <Button size="sm" onClick={retry}>
          Повторить
        </Button>
      </p>
    );
  if (load === "loading")
    return (
      <p className="relative text-[11px] text-text-tertiary">
        Мозаика 2024: загрузка тайлов…
        <span aria-hidden className="absolute inset-x-0 -bottom-1 h-0.5 bg-line-hairline" />
      </p>
    );
  return null;
}

function BasemapNote() {
  const basemapId = useMapLayersStore((state) => state.basemapId);
  const setBasemap = useMapLayersStore((state) => state.setBasemap);
  if (basemapId === "s2-mosaic") return <MosaicStatus />;
  return (
    <div className="flex flex-col items-start gap-1.5 border-t border-line-hairline pt-2">
      <p className="text-[12px] leading-4 text-text-secondary">
        Подложка сейчас не «Мозаика S2»: мозаика 2024 скрыта, сравниваются только контуры A и B.
      </p>
      <Button size="sm" onClick={() => setBasemap("s2-mosaic")}>
        Включить «Мозаика S2»
      </Button>
    </div>
  );
}

export function CompareMethodBox() {
  const frame = useFrameWidth();
  const phone = useIsPhoneWidth();
  if (phone) return null;
  const inset = frame + FURNITURE_GAP_PX;
  return (
    <section
      aria-label="Способ сравнения"
      className="pointer-events-auto absolute z-[2] flex w-[304px] flex-col gap-2 border border-line-control bg-surface-panel p-2.5"
      style={{ left: inset, bottom: inset }}
    >
      <Segmented
        label="Способ сравнения"
        value="swipe"
        options={COMPARE_METHODS}
        onChange={() => undefined}
      />
      <p className="text-[12px] leading-4 text-text-secondary">{COMPARE_HONESTY_NOTE}</p>
      <BasemapNote />
    </section>
  );
}
