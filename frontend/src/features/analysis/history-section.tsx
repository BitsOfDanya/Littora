"use client";

import { useState } from "react";
import { AREAS_OF_INTEREST } from "@/config/aois";
import { fitAoi } from "@/features/map/camera";
import { useMainMap } from "@/features/map/use-main-map";
import type { AnalysisListItem, ResultStatus } from "@/lib/api/analyses";
import { describeApiError } from "@/lib/api/errors";
import { formatUtcDateTime } from "@/lib/format/time";
import { useAnalysisStore } from "@/state/analysis-store";
import { useWorkspaceStore } from "@/state/workspace-store";
import { cn } from "@/ui/cn";
import { PanelSection } from "@/ui/section";
import { Segmented } from "@/ui/segmented";
import { StatusTag } from "@/ui/status-tag";
import { RESULT_STATUS_ORDER, STATUS_LABELS, STATUS_TONES } from "./analysis-copy";
import { formatDay } from "./format";
import { FIELD_CONTROL } from "./request-section";
import { useAnalysisHistory } from "./use-analysis";

const SCOPE_OPTIONS = [
  { value: "aoi", label: "этот участок" },
  { value: "all", label: "все участки" },
] as const;

const VISIBLE_ROWS = 30;

function HistoryRow({
  item,
  current,
  onOpen,
}: {
  item: AnalysisListItem;
  current: boolean;
  onOpen: () => void;
}) {
  return (
    <li
      className={cn(
        "border-b border-line-hairline last:border-b-0",
        current && "shadow-[inset_3px_0_0_var(--text-primary)]",
      )}
    >
      <button
        type="button"
        aria-current={current || undefined}
        onClick={onOpen}
        className="grid w-full grid-cols-[minmax(0,1fr)_auto] items-center gap-x-2 gap-y-0.5 px-2 py-1.5 text-left hover:bg-surface-raised"
      >
        <span className="truncate text-[12px] leading-4 text-text-primary">
          <span className="font-mono">{formatDay(item.request.date)}</span> ·{" "}
          {item.request.aoi_name ?? "район"}
        </span>
        <StatusTag tone={STATUS_TONES[item.status.status]} className="h-[18px] px-1.5 text-[11px]">
          {item.status.label}
        </StatusTag>
        <span className="col-span-2 truncate font-mono text-[11px] leading-[14px] text-text-tertiary">
          {item.scene_id ?? "без снимка"} · измерений {item.observations} · расчёт{" "}
          {formatUtcDateTime(item.computed_at)}
        </span>
      </button>
    </li>
  );
}

export function HistorySection() {
  const aoiId = useWorkspaceStore((state) => state.aoiId);
  const setAoi = useWorkspaceStore((state) => state.setAoi);
  const analysisId = useAnalysisStore((state) => state.analysisId);
  const setAnalysis = useAnalysisStore((state) => state.setAnalysis);
  const status = useAnalysisStore((state) => state.historyStatus);
  const setStatus = useAnalysisStore((state) => state.setHistoryStatus);
  const allAreas = useAnalysisStore((state) => state.historyAllAreas);
  const setAllAreas = useAnalysisStore((state) => state.setHistoryAllAreas);
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const map = useMainMap();
  const history = useAnalysisHistory({
    status,
    aoiId: allAreas ? null : aoiId,
    dateFrom: dateFrom || null,
    dateTo: dateTo || null,
  });
  const items = history.data ?? [];

  const open = (item: AnalysisListItem) => {
    const target = AREAS_OF_INTEREST.find((aoi) => aoi.id === item.request.aoi_id);
    if (target && target.id !== aoiId) {
      setAoi(target.id);
      if (map) fitAoi(map, target);
    }
    setAnalysis(item.id);
  };

  return (
    <PanelSection index="05" title="Сохранённые запросы">
      <div className="flex flex-col gap-2">
        <Segmented<"aoi" | "all">
          label="Какие запросы показать"
          value={allAreas ? "all" : "aoi"}
          options={SCOPE_OPTIONS}
          onChange={(value) => setAllAreas(value === "all")}
        />
        <div className="grid grid-cols-[minmax(0,1fr)_minmax(0,1fr)] gap-2">
          <label className="col-span-2 flex flex-col gap-1 text-[12px] text-text-secondary">
            Статус
            <select
              className={FIELD_CONTROL}
              value={status ?? ""}
              onChange={(event) =>
                setStatus(event.target.value ? (event.target.value as ResultStatus) : null)
              }
            >
              <option value="">все статусы</option>
              {RESULT_STATUS_ORDER.map((entry) => (
                <option key={entry} value={entry}>
                  {STATUS_LABELS[entry]}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-[12px] text-text-secondary">
            Дата с
            <input
              type="date"
              className={FIELD_CONTROL}
              value={dateFrom}
              onChange={(event) => setDateFrom(event.target.value)}
            />
          </label>
          <label className="flex flex-col gap-1 text-[12px] text-text-secondary">
            по
            <input
              type="date"
              className={FIELD_CONTROL}
              value={dateTo}
              onChange={(event) => setDateTo(event.target.value)}
            />
          </label>
        </div>
      </div>
      {history.isError ? (
        <p className="text-[12px] leading-4 text-state-alarm">
          История недоступна: {describeApiError(history.error)}
        </p>
      ) : items.length === 0 ? (
        <p className="text-[12px] leading-4 text-text-secondary">
          {history.isPending ? "Загружаем историю…" : "Запросов с такими условиями нет."}
        </p>
      ) : (
        <ul className="flex max-h-[280px] flex-col overflow-y-auto rounded-[var(--radius-ctl)] border border-line-hairline">
          {items.slice(0, VISIBLE_ROWS).map((item) => (
            <HistoryRow
              key={item.id}
              item={item}
              current={item.id === analysisId}
              onOpen={() => open(item)}
            />
          ))}
        </ul>
      )}
      {items.length > VISIBLE_ROWS ? (
        <p className="text-[11px] text-text-tertiary">
          Показаны последние {VISIBLE_ROWS} из {items.length} — сузьте фильтр.
        </p>
      ) : null}
    </PanelSection>
  );
}
