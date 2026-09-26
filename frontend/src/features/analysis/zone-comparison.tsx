"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { type FieldObservation, getObservations } from "@/lib/api/case";
import type { Analysis } from "@/lib/api/analyses";
import { formatNumber, formatPercent } from "@/lib/format/numbers";
import { queryKeys } from "@/lib/query/query-keys";
import { cn } from "@/ui/cn";
import { CONCENTRATION_UNIT, profileLabel } from "./analysis-copy";
import { formatConcentration, formatDay, formatDelta } from "./format";
import { coverageArea, coverageRange, type RealZone } from "./zones";

const EARTH_KM = 6371.0088;
const NEAREST = 5;
const COMPARABLE_KM = 50;
const COMPARABLE_DAYS = 3;
const DAY_MS = 86_400_000;

type Nearby = { feature: FieldObservation; km: number; days: number | null };

export function haversineKm(a: readonly [number, number], b: readonly [number, number]): number {
  const [lon1, lat1] = a.map((value) => (value * Math.PI) / 180);
  const [lon2, lat2] = b.map((value) => (value * Math.PI) / 180);
  const h =
    Math.sin((lat2 - lat1) / 2) ** 2 +
    Math.cos(lat1) * Math.cos(lat2) * Math.sin((lon2 - lon1) / 2) ** 2;
  return 2 * EARTH_KM * Math.asin(Math.min(1, Math.sqrt(h)));
}

function anchor(feature: FieldObservation): [number, number] {
  if (feature.geometry.type === "Point") {
    const [lon, lat] = feature.geometry.coordinates;
    return [lon, lat];
  }
  const points = feature.geometry.coordinates;
  const [lon, lat] = points[Math.floor(points.length / 2)] ?? points[0];
  return [lon, lat];
}

export function nearestObservations(
  features: readonly FieldObservation[],
  centroid: readonly [number, number],
  sceneDay: string | null,
): Nearby[] {
  const reference = sceneDay ? Date.parse(`${sceneDay}T00:00:00Z`) : null;
  return features
    .map((feature) => ({
      feature,
      km: haversineKm(centroid, anchor(feature)),
      days:
        reference === null
          ? null
          : Math.round((Date.parse(`${feature.properties.date}T00:00:00Z`) - reference) / DAY_MS),
    }))
    .sort((a, b) => a.km - b.km)
    .slice(0, NEAREST);
}

function comparable(item: Nearby): boolean {
  return item.km <= COMPARABLE_KM && item.days !== null && Math.abs(item.days) <= COMPARABLE_DAYS;
}

export function ZoneComparison({ analysis, zone }: { analysis: Analysis; zone: RealZone }) {
  const observations = useQuery({
    queryKey: queryKeys.case.observations({}),
    queryFn: ({ signal }) => getObservations({}, signal),
    staleTime: Infinity,
  });
  const sceneDay = analysis.scene?.acquired_at.slice(0, 10) ?? null;
  const nearby =
    zone.centroid && observations.data
      ? nearestObservations(observations.data, zone.centroid, sceneDay)
      : [];
  const matched = nearby.filter(comparable);
  const coverage = zone.coverage;

  return (
    <div className="flex flex-col gap-2 text-[12px] leading-4">
      <div className="grid grid-cols-2 gap-2">
        <div className="rounded-[2px] border border-line-hairline p-2">
          <p className="text-[11px] font-semibold text-text-secondary">Спутник · эта зона</p>
          <p className="mt-1 font-mono text-[13px] text-text-primary">
            {formatNumber(zone.pixels ?? 0)} пикс. 10 м
          </p>
          <p className="text-text-secondary">
            {coverage
              ? `покрытие ~${formatPercent(coverage.mean, 0)} (${coverageRange(coverage)}), ${coverageArea(coverage)}`
              : "доля покрытия не оценена"}
          </p>
          <p className="mt-1 text-[11px] text-text-tertiary">модельная оценка по снимку</p>
        </div>
        <div className="rounded-[2px] border border-line-hairline p-2">
          <p className="text-[11px] font-semibold text-text-secondary">Судно · ближайшее</p>
          {nearby[0] ? (
            <>
              <p className="mt-1 font-mono text-[13px] text-text-primary">
                {formatConcentration(nearby[0].feature.properties.concentration)}{" "}
                {CONCENTRATION_UNIT}
              </p>
              <p className="text-text-secondary">
                {formatNumber(nearby[0].km, nearby[0].km < 10 ? 1 : 0)} км ·{" "}
                {formatDelta(nearby[0].days)}
              </p>
            </>
          ) : (
            <p className="mt-1 text-text-secondary">
              {observations.isPending ? "загружаем измерения…" : "измерений нет"}
            </p>
          )}
          <p className="mt-1 text-[11px] text-text-tertiary">измерение с судна</p>
        </div>
      </div>
      <p className={cn(matched.length ? "text-state-ok" : "text-text-secondary")}>
        {matched.length
          ? `${matched.length} измер. в пределах ${COMPARABLE_KM} км и ±${COMPARABLE_DAYS} сут от снимка — сопоставимы по месту и времени.`
          : `Измерений ближе ${COMPARABLE_KM} км и ±${COMPARABLE_DAYS} сут от снимка нет: сравнение только справочное.`}
      </p>
      {nearby.length ? (
        <table className="w-full border-collapse">
          <thead>
            <tr className="border-b border-text-primary text-left text-[11px] text-text-secondary">
              <th className="pb-1 font-medium">Измерение</th>
              <th className="pb-1 text-right font-medium">{CONCENTRATION_UNIT}</th>
              <th className="pb-1 text-right font-medium">км</th>
              <th className="pb-1 text-right font-medium">сдвиг</th>
            </tr>
          </thead>
          <tbody>
            {nearby.map((item) => (
              <tr
                key={item.feature.id}
                className={cn(
                  "border-b border-line-hairline",
                  !comparable(item) && "text-text-tertiary",
                )}
              >
                <td className="py-1">
                  <span className="font-mono">{item.feature.properties.sample_id}</span>
                  <span className="block text-[11px] text-text-tertiary">
                    {formatDay(item.feature.properties.date)} ·{" "}
                    {profileLabel(item.feature.properties.measurement_profile)}
                  </span>
                </td>
                <td className="py-1 text-right font-mono">
                  {formatConcentration(item.feature.properties.concentration)}
                </td>
                <td className="py-1 text-right font-mono">
                  {formatNumber(item.km, item.km < 10 ? 1 : 0)}
                </td>
                <td className="py-1 text-right">{formatDelta(item.days)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : null}
      <p className="text-[11px] leading-[14px] text-text-tertiary">
        Судно считает отдельные предметы от 2–2,5 см на площади трансекта, спутник видит скопления,
        заметные в пикселе 10 м. На 7 парах того же дня в Чёрном море судно насчитало 190–590{" "}
        {CONCENTRATION_UNIT}, а детектор выделил от 0 до 58 пикселей из ~1,1 млн без связи с
        концентрацией — поэтому концентрация по площади зоны не выводится.{" "}
        <Link href="/models#models-pairs" className="underline hover:text-text-primary">
          Пары судно — спутник
        </Link>
      </p>
    </div>
  );
}
