"use client";

import { easeToIfOutside } from "@/features/map/camera";
import { useMainMap } from "@/features/map/use-main-map";
import type { ObservationProperties } from "@/lib/api/case";
import { formatNumber } from "@/lib/format/numbers";
import { type ObservationDates, useAnalysisStore } from "@/state/analysis-store";
import { cn } from "@/ui/cn";
import { KeyValue, KeyValueList } from "@/ui/key-value";
import { PanelSection } from "@/ui/section";
import { Segmented } from "@/ui/segmented";
import { CONCENTRATION_UNIT, MEASUREMENT_NOTE, profileLabel } from "./analysis-copy";
import { formatConcentration, formatDay, formatDelta } from "./format";
import { type TimedObservation, useObservationsView } from "./use-observations-view";

const DATE_OPTIONS = [
  { value: "all", label: "все даты" },
  { value: "window", label: "в окне снимка" },
] as const;

export function MeasurementGlyph({ value, faded }: { value: number | null; faded?: boolean }) {
  const hollow = value === null || value === 0;
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 14 14"
      aria-hidden
      className={cn("shrink-0 text-text-primary", faded && "opacity-45")}
    >
      <circle
        cx="7"
        cy="7"
        r="5"
        fill={hollow ? "none" : "currentColor"}
        stroke="currentColor"
        strokeWidth="1.4"
      />
    </svg>
  );
}

function timeRange(properties: ObservationProperties): string {
  const start = properties.time_start?.slice(0, 5);
  const end = properties.time_end?.slice(0, 5);
  if (start && end) return `${start}–${end}`;
  return start ?? end ?? "время не указано";
}

function ObservationDetails({ properties }: { properties: ObservationProperties }) {
  const counted =
    properties.items !== null && properties.area_km2 !== null
      ? `${formatNumber(properties.items, 0)} шт. на ${formatNumber(properties.area_km2, 3)} км²`
      : "в источнике не указано";
  return (
    <KeyValueList className="border-t border-line-hairline pt-1">
      <KeyValue label="Источник">
        <span className="font-sans text-[12px] font-normal">{properties.source_short}</span>
      </KeyValue>
      <KeyValue label="Метод">
        <span className="font-sans text-[12px] font-normal">{properties.sampling_method}</span>
      </KeyValue>
      <KeyValue label="Размер · материал">
        <span className="font-sans text-[12px] font-normal">
          {properties.size_class} · {properties.material}
        </span>
      </KeyValue>
      <KeyValue label="Время, UTC">{timeRange(properties)}</KeyValue>
      <KeyValue label="Учтено">{counted}</KeyValue>
      <KeyValue label="Проверка C = N/A">
        <span className="font-sans text-[12px] font-normal">{properties.check_label}</span>
      </KeyValue>
      <KeyValue label="Пара со снимком">
        <span className="font-sans text-[12px] font-normal">
          {properties.pair_reason ?? "событие не сопоставлялось"}
        </span>
      </KeyValue>
      {properties.pair_scene_id ? (
        <KeyValue label="Сцена пары">
          <span className="font-mono text-[11px] font-normal break-all">
            {properties.pair_scene_id}
          </span>
        </KeyValue>
      ) : null}
      <KeyValue label="Лицензия">
        <span className="font-sans text-[12px] font-normal">{properties.source_license}</span>
      </KeyValue>
    </KeyValueList>
  );
}

function ObservationRow({
  item,
  selected,
  hasReference,
  onSelect,
}: {
  item: TimedObservation;
  selected: boolean;
  hasReference: boolean;
  onSelect: () => void;
}) {
  const properties = item.feature.properties;
  return (
    <li
      className={cn(
        "border-b border-line-hairline last:border-b-0",
        selected && "shadow-[inset_3px_0_0_var(--accent-selection)]",
      )}
    >
      <button
        type="button"
        aria-pressed={selected}
        onClick={onSelect}
        className="grid w-full grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-x-2 px-2 py-1.5 text-left hover:bg-surface-raised"
      >
        <MeasurementGlyph value={properties.concentration} faded={hasReference && !item.inWindow} />
        <span className="flex min-w-0 flex-col">
          <span className="truncate font-mono text-[12px] leading-4 text-text-primary">
            {properties.sample_id} · {properties.event_id.split(":").at(-1)}
          </span>
          <span className="truncate text-[11px] leading-[14px] text-text-secondary">
            {formatDay(properties.date)} · {profileLabel(properties.measurement_profile)}
          </span>
        </span>
        <span className="flex flex-col items-end">
          <span className="font-mono text-[13px] leading-4 font-medium text-text-primary">
            {formatConcentration(properties.concentration)}
          </span>
          <span
            className={cn(
              "text-[11px] leading-[14px]",
              hasReference && item.inWindow ? "text-state-ok" : "text-text-tertiary",
            )}
          >
            {hasReference ? formatDelta(item.deltaDays) : CONCENTRATION_UNIT}
          </span>
        </span>
      </button>
      {selected ? (
        <div className="px-2 pb-2">
          <ObservationDetails properties={properties} />
        </div>
      ) : null}
    </li>
  );
}

export function MeasurementsSection({ hasAnalysis }: { hasAnalysis: boolean }) {
  const view = useObservationsView();
  const map = useMainMap();
  const selectedId = useAnalysisStore((state) => state.observationId);
  const selectObservation = useAnalysisStore((state) => state.selectObservation);
  const setDates = useAnalysisStore((state) => state.setObservationDates);
  const inWindow = view.listed.filter((item) => item.inWindow).length;
  const hasReference = view.reference !== null;

  const select = (item: TimedObservation) => {
    const next = item.feature.id === selectedId ? null : item.feature.id;
    selectObservation(next);
    if (next && map) easeToIfOutside(map, item.point);
  };

  return (
    <PanelSection
      index="04"
      title="Полевые измерения"
      aside={
        <span className="font-mono text-[12px] text-text-secondary">{CONCENTRATION_UNIT}</span>
      }
    >
      <p className="text-[12px] leading-4 text-text-secondary">
        {view.total === 0
          ? view.isPending
            ? "Загружаем измерения кейса…"
            : view.isError
              ? "Измерения кейса недоступны: сервер не отдал данные."
              : "В этом районе нет натурных измерений кейса."
          : `${view.total} ${hasAnalysis ? "в районе запроса" : "на участке"}${hasReference ? ` · ${inWindow} в окне ±${view.windowDays} сут от снимка ${formatDay(view.reference ?? "")}` : ""}`}
      </p>
      {view.total > 0 ? (
        <>
          <Segmented<ObservationDates>
            label="Фильтр измерений по дате"
            value={view.dates}
            options={DATE_OPTIONS}
            onChange={setDates}
          />
          <ul className="flex max-h-[360px] flex-col overflow-y-auto rounded-[var(--radius-ctl)] border border-line-hairline">
            {view.listed.map((item) => (
              <ObservationRow
                key={item.feature.id}
                item={item}
                selected={item.feature.id === selectedId}
                hasReference={hasReference}
                onSelect={() => select(item)}
              />
            ))}
          </ul>
          <p className="text-[11px] leading-[14px] text-text-tertiary">{MEASUREMENT_NOTE}</p>
        </>
      ) : null}
    </PanelSection>
  );
}
