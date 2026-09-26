"use client";

import type { Layer } from "@deck.gl/core";
import { ScatterplotLayer } from "@deck.gl/layers";
import type { MapMouseEvent } from "maplibre-gl";
import { useEffect, useMemo } from "react";
import { createPortal } from "react-dom";
import { create } from "zustand";
import { useCurrentAnalysis } from "@/features/analysis/use-analysis";
import { type Anchored, UNDER_LABELS } from "@/features/map/deck/anchors";
import { useDeckLayers } from "@/features/map/deck/use-deck-layers";
import { useMapPalette } from "@/features/map/use-map-palette";
import { useMainMap } from "@/features/map/use-main-map";
import { useStatusHintStore } from "@/features/shell/status-hint-store";
import { getPixel, type PixelValues } from "@/lib/api/analyses";
import { formatNumber, formatPercent } from "@/lib/format/numbers";

type Reading =
  | { state: "loading"; lon: number; lat: number }
  | { state: "ready"; lon: number; lat: number; values: PixelValues }
  | { state: "error"; lon: number; lat: number; message: string };

type ProbeState = {
  active: boolean;
  reading: Reading | null;
  toggle: () => void;
  setActive: (active: boolean) => void;
  setReading: (reading: Reading | null) => void;
};

export const usePixelProbeStore = create<ProbeState>((set) => ({
  active: false,
  reading: null,
  toggle: () => set((state) => ({ active: !state.active, reading: null })),
  setActive: (active) => set({ active, reading: null }),
  setReading: (reading) => set({ reading }),
}));

const HINT = "Лупа: щелчок по карте — значения пикселя 10 м · Esc — выключить";

function value(number: number | null | undefined, digits = 3): string {
  return number === null || number === undefined ? "—" : formatNumber(number, digits);
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-4">
      <span className="text-text-secondary">{label}</span>
      <span className="font-mono text-text-primary">{children}</span>
    </div>
  );
}

function ProbeCard({ reading, onClose }: { reading: Reading; onClose: () => void }) {
  const values = reading.state === "ready" ? reading.values : null;
  return (
    <div
      role="dialog"
      aria-label="Значения пикселя"
      className="pointer-events-auto fixed bottom-12 left-1/2 z-40 w-[320px] -translate-x-1/2 rounded-[2px] border border-line-control bg-surface-panel p-3 text-[12px] leading-4 shadow-lg"
    >
      <div className="mb-2 flex items-baseline justify-between gap-2">
        <span className="font-semibold text-text-primary">Пиксель 10 м</span>
        <button
          type="button"
          onClick={onClose}
          className="text-text-secondary hover:text-text-primary"
          aria-label="Закрыть"
        >
          ×
        </button>
      </div>
      <p className="mb-2 font-mono text-[11px] text-text-tertiary">
        {reading.lat.toFixed(5)}, {reading.lon.toFixed(5)}
      </p>
      {reading.state === "loading" ? <p className="text-text-secondary">Читаем значения…</p> : null}
      {reading.state === "error" ? <p className="text-state-alarm">{reading.message}</p> : null}
      {values && !values.inside ? (
        <p className="text-text-secondary">Точка вне района анализа.</p>
      ) : null}
      {values?.inside ? (
        <div className="flex flex-col gap-1">
          <Row label="Вероятность мусора (калибр.)">
            {value(values.probability, 2)}{" "}
            <span className="text-text-secondary">
              {values.above_threshold ? "≥" : "<"} порог {value(values.threshold, 2)}
            </span>
          </Row>
          <Row label="Зона детектора">{values.zone_id ?? "нет"}</Row>
          <Row label="Класс маски SCL">{values.scl?.label ?? "—"}</Row>
          <Row label="FDI">{value(values.fdi, 4)}</Row>
          <Row label="NDVI">{value(values.ndvi, 3)}</Row>
          <Row label="Доля покрытия (оценка)">
            {values.coverage === null || values.coverage === undefined
              ? "—"
              : formatPercent(values.coverage, 0)}
          </Row>
          <div className="mt-1 border-t border-line-hairline pt-1">
            {Object.entries(values.reflectance ?? {}).map(([band, reflectance]) => (
              <Row key={band} label={`Отражение ${band}`}>
                {value(reflectance, 4)}
              </Row>
            ))}
          </div>
          <p className="mt-1 text-[11px] leading-[14px] text-text-tertiary">
            Отражение L2A, вероятность — после калибровки; доля покрытия — оценка смешения с водным
            фоном в NIR, не измерение.
          </p>
        </div>
      ) : null}
    </div>
  );
}

export function PixelProbe() {
  const active = usePixelProbeStore((state) => state.active);
  const setActive = usePixelProbeStore((state) => state.setActive);
  const map = useMainMap();
  const analysis = useCurrentAnalysis().data ?? null;
  const palette = useMapPalette();
  const setHint = useStatusHintStore((state) => state.setHint);
  const reading = usePixelProbeStore((state) => state.reading);
  const setReading = usePixelProbeStore((state) => state.setReading);
  const analysisId = analysis?.id ?? null;

  useEffect(() => {
    if (!active) {
      setHint(null);
      return;
    }
    setHint(analysisId ? HINT : "Лупа работает после анализа района");
    return () => setHint(null);
  }, [active, analysisId, setHint]);

  useEffect(() => {
    if (!map || !active) return;
    const canvas = map.getCanvas();
    const previous = canvas.style.cursor;
    canvas.style.cursor = "crosshair";
    let controller: AbortController | null = null;
    const onClick = (event: MapMouseEvent) => {
      const { lng, lat } = event.lngLat;
      if (!analysisId) {
        setReading({ state: "error", lon: lng, lat, message: "Сначала запустите анализ района." });
        return;
      }
      controller?.abort();
      controller = new AbortController();
      setReading({ state: "loading", lon: lng, lat });
      getPixel(analysisId, lng, lat, controller.signal)
        .then((values) => setReading({ state: "ready", lon: lng, lat, values }))
        .catch((error: unknown) => {
          if (error instanceof DOMException && error.name === "AbortError") return;
          setReading({
            state: "error",
            lon: lng,
            lat,
            message: error instanceof Error ? error.message : "Значения не получены",
          });
        });
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setActive(false);
    };
    map.on("click", onClick);
    window.addEventListener("keydown", onKey);
    return () => {
      controller?.abort();
      map.off("click", onClick);
      window.removeEventListener("keydown", onKey);
      canvas.style.cursor = previous;
    };
  }, [map, active, analysisId, setActive, setReading]);

  const layers = useMemo(() => {
    const list: Layer[] = [];
    if (active && reading)
      list.push(
        new ScatterplotLayer<{ position: [number, number] }, Anchored>({
          id: "pixel-probe:point",
          ...UNDER_LABELS,
          data: [{ position: [reading.lon, reading.lat] }],
          getPosition: (entry) => entry.position,
          getRadius: 6,
          radiusUnits: "pixels",
          stroked: true,
          filled: false,
          getLineColor: palette.alarm,
          lineWidthUnits: "pixels",
          getLineWidth: 2,
        }),
      );
    return list;
  }, [active, reading, palette]);
  useDeckLayers("pixel-probe", layers);

  if (!active || !reading || typeof document === "undefined") return null;
  return createPortal(
    <ProbeCard reading={reading} onClose={() => setReading(null)} />,
    document.body,
  );
}
