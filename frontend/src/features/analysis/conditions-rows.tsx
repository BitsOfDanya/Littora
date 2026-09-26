"use client";

import { compassPoint } from "@/features/forecast/drift-math";
import type { Analysis } from "@/lib/api/analyses";
import { formatNumber } from "@/lib/format/numbers";
import { formatUtcTime } from "@/lib/format/time";
import { KeyValue } from "@/ui/key-value";
import { useAnalysisConditions } from "./use-analysis";

function fromDirection(degrees: number | null | undefined): string {
  if (degrees === null || degrees === undefined) return "";
  return ` · с ${compassPoint(degrees)} ${formatNumber(degrees)}°`;
}

export function ConditionsRows({ analysis }: { analysis: Analysis }) {
  const conditions = useAnalysisConditions(analysis);
  const data = conditions.data;
  if (conditions.isPending && conditions.fetchStatus !== "idle")
    return (
      <KeyValue label="Ветер и волнение">
        <span className="font-sans text-[12px] font-normal text-text-tertiary">
          запрашиваем Open-Meteo…
        </span>
      </KeyValue>
    );
  if (!data) return null;
  const hour = formatUtcTime(data.at);
  return (
    <>
      {data.wind ? (
        <KeyValue label="Ветер 10 м" hint={`${hour} · ${data.wind.source}`}>
          {formatNumber(data.wind.speed_ms, 1)} м/с{fromDirection(data.wind.from_deg)}
        </KeyValue>
      ) : null}
      {data.waves ? (
        <KeyValue label="Волнение" hint={`${hour} · ${data.waves.source}`}>
          {formatNumber(data.waves.height_m, 1)} м
          {data.waves.period_s ? ` · ${formatNumber(data.waves.period_s, 1)} с` : ""}
          {fromDirection(data.waves.from_deg)}
        </KeyValue>
      ) : null}
      {data.messages.length ? (
        <div className="py-1 text-[11px] leading-[14px] text-text-tertiary">
          {data.messages.join(" · ")}
        </div>
      ) : null}
    </>
  );
}
