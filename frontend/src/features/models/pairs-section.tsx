"use client";

import { useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useState } from "react";
import type { SatelliteLinkCheck, SatellitePairRow } from "@/data/models";
import type { BBox } from "@/domain/geo";
import { useRunAnalysis } from "@/features/analysis/use-analysis";
import { fitTo } from "@/features/map/camera";
import { useMainMap } from "@/features/map/use-main-map";
import { type CaseEvent, getEvents } from "@/lib/api/case";
import { formatNumber } from "@/lib/format/numbers";
import { Button } from "@/ui/button";
import { cn } from "@/ui/cn";
import { ReportSection } from "./report-section";

const HEAD = "pb-2 text-[12px] leading-4 font-medium text-text-secondary align-bottom";
const CELL = "py-2 align-middle text-[12px] leading-4 text-text-secondary";
const TARGET = "litter-visual";

function bounds(event: CaseEvent): BBox | null {
  const geometry = event.geometry;
  const points: [number, number][] =
    geometry.type === "Point"
      ? [geometry.coordinates as [number, number]]
      : geometry.type === "LineString"
        ? (geometry.coordinates as [number, number][])
        : geometry.type === "Polygon"
          ? (geometry.coordinates[0] as [number, number][])
          : [];
  if (!points.length) return null;
  const lons = points.map(([lon]) => lon);
  const lats = points.map(([, lat]) => lat);
  const round = (value: number) => Math.round(value * 1e4) / 1e4;
  return [
    round(Math.min(...lons)),
    round(Math.min(...lats)),
    round(Math.max(...lons)),
    round(Math.max(...lats)),
  ];
}

function sceneDay(sceneId: string): string {
  const match = /_(\d{4})(\d{2})(\d{2})T/.exec(sceneId);
  return match ? `${match[1]}-${match[2]}-${match[3]}` : "";
}

function OpenButton({ pair, events }: { pair: SatellitePairRow; events: CaseEvent[] }) {
  const run = useRunAnalysis();
  const router = useRouter();
  const map = useMainMap();
  const [failed, setFailed] = useState<string | null>(null);
  const event = events.find((item) => item.properties.event_id === pair.eventId);
  const bbox = event ? bounds(event) : null;
  const open = () => {
    if (!bbox) return;
    setFailed(null);
    run.mutate(
      {
        bbox: [...bbox],
        date: sceneDay(pair.sceneId),
        window_days: 0,
        scene_id: pair.sceneId,
        target: TARGET,
        aoi_id: null,
        aoi_name: `Пара ${pair.eventId.split(":").at(-1)} · судно и спутник`,
      },
      {
        onSuccess: () => {
          router.push("/monitor");
          if (map) fitTo(map, bbox);
        },
        onError: (error) => setFailed(error instanceof Error ? error.message : "не удалось"),
      },
    );
  };
  return (
    <span className="flex flex-col items-end gap-0.5">
      <Button size="sm" onClick={open} disabled={!bbox || run.isPending}>
        {run.isPending ? "Считаем…" : "Открыть на карте"}
      </Button>
      {failed ? <span className="text-[11px] text-state-alarm">{failed}</span> : null}
    </span>
  );
}

export function PairsSection({ link, index }: { link: SatelliteLinkCheck; index: number }) {
  const events = useQuery({
    queryKey: ["case", "events", "accepted"],
    queryFn: ({ signal }) => getEvents(signal),
    staleTime: Infinity,
  });
  const features = events.data?.features ?? [];
  return (
    <ReportSection id="pairs" index={index}>
      <table className="w-full border-collapse">
        <caption className="sr-only">
          Полевые измерения с судна и детектор на снимке Sentinel-2 той же даты
        </caption>
        <thead>
          <tr className="border-b border-text-primary">
            <th scope="col" className={cn(HEAD, "text-left")}>
              Трансект · снимок
            </th>
            <th scope="col" className={cn(HEAD, "pl-3 text-right")}>
              Судно, шт./км²
            </th>
            <th scope="col" className={cn(HEAD, "pl-3 text-right")}>
              Спутник: пикселей воды
            </th>
            <th scope="col" className={cn(HEAD, "pl-3 text-right")}>
              Пикселей выше порога
            </th>
            <th scope="col" className={cn(HEAD, "pl-3 text-right")}>
              Вероятность, p99
            </th>
            <th scope="col" className={cn(HEAD, "pl-3 text-right")}>
              FDI, p99
            </th>
            <th scope="col" className={cn(HEAD, "pl-3 text-right")}>
              <span className="sr-only">Действие</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {link.pairs.map((pair) => (
            <tr key={`${pair.eventId}-${pair.sceneId}`} className="border-b border-line-hairline">
              <th scope="row" className={cn(CELL, "text-left font-normal")}>
                <span className="font-mono text-text-primary">{pair.eventId}</span>
                <span className="block font-mono text-[11px] text-text-tertiary">
                  {pair.sceneId}
                </span>
              </th>
              <td className={cn(CELL, "pl-3 text-right font-mono text-text-primary")}>
                {pair.concentration === null ? "—" : formatNumber(pair.concentration, 0)}
              </td>
              <td className={cn(CELL, "pl-3 text-right font-mono")}>
                {pair.waterPixels === null ? "—" : formatNumber(pair.waterPixels)}
              </td>
              <td className={cn(CELL, "pl-3 text-right font-mono")}>
                {pair.detectedShare === null || pair.waterPixels === null
                  ? "—"
                  : formatNumber(Math.round(pair.detectedShare * pair.waterPixels))}
              </td>
              <td className={cn(CELL, "pl-3 text-right font-mono")}>
                {pair.probabilityP99 === null ? "—" : formatNumber(pair.probabilityP99, 5)}
              </td>
              <td className={cn(CELL, "pl-3 text-right font-mono")}>
                {pair.fdiP99 === null ? "—" : formatNumber(pair.fdiP99, 4)}
              </td>
              <td className={cn(CELL, "pl-3 text-right")}>
                <OpenButton pair={pair} events={features} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="mt-3 text-[12px] leading-4 text-text-secondary">
        Судно насчитало на этих трансектах{" "}
        {formatNumber(Math.min(...link.pairs.map((pair) => pair.concentration ?? Infinity)), 0)}–
        {formatNumber(Math.max(...link.pairs.map((pair) => pair.concentration ?? 0)), 0)} шт./км²
        предметов от 2,5 см, а детектор на снимке того же дня почти ничего не выделил: от 0 до 58
        пикселей выше порога из ~1,1 млн пикселей воды, не больше 0,005 %. Отдельные предметы такого
        размера в пикселе 10 м не видны, спутник замечает только скопления. Ни один признак снимка
        не связан с измеренной концентрацией значимо (Спирмен, 7 пар), поэтому концентрация по
        снимку не выводится, а в сервисе остаётся полевая модель со статусом «исследовательская
        оценка». Кнопка запускает анализ района пары на её снимке — снимок, маска качества,
        композиты, зоны и полевое измерение видны на карте.
      </p>
    </ReportSection>
  );
}
