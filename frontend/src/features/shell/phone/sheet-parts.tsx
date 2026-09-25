"use client";

import { type KeyboardEvent, type ReactNode } from "react";
import type { WorkspaceModeId } from "@/config/modes";
import { useCandidates } from "@/data/candidates";
import { ApiStatusLabel } from "@/features/system/backend-status";
import { useApiStatus } from "@/features/system/use-api-status";
import { type SheetDetent, useShellUiStore } from "@/state/shell-ui-store";
import { useWorkspaceStore } from "@/state/workspace-store";
import { DemoTag } from "@/ui/demo-mark";
import { IconChevronDown, IconChevronUp, IconLayers } from "@/ui/icons";
import { SeverityGlyph } from "@/ui/indicators";
import { countRu } from "../orientation/plural";
import { eventStamp, rowAccessibleName } from "../queue/queue-copy";
import type { QueueRow } from "../queue/use-queue";
import { useSelectEventObject } from "../queue/use-select-event-object";
import { CoordinateText } from "../status/coord-readout";
import { DETENT_LABEL } from "./sheet-detents";
import type { SheetDrag } from "./use-sheet-drag";

export const PANEL_TITLE: Record<WorkspaceModeId, string> = {
  monitor: "Досье",
  timeline: "Сравнение A/B",
  forecast: "Прогноз дрейфа",
  survey: "План обследования",
  models: "Модели",
};

export function LayersSummary() {
  const candidates = useCandidates();
  if (candidates.origin === "none") return <span>Слои и объекты</span>;
  return (
    <span className="flex items-center gap-1.5">
      <span>{countRu(candidates.data.length, ["объект", "объекта", "объектов"])}</span>
      {candidates.origin === "demo" ? <DemoTag /> : null}
      <span className="text-text-tertiary">· Слои</span>
    </span>
  );
}

export function InspectorSummary({ mode }: { mode: WorkspaceModeId }) {
  const selectedId = useWorkspaceStore((state) => state.selectedCandidateId);
  return (
    <span className="flex min-w-0 items-center gap-1.5">
      <span>{PANEL_TITLE[mode]}</span>
      {selectedId ? (
        <span className="font-mono text-[12px] text-text-secondary">{selectedId}</span>
      ) : null}
    </span>
  );
}

export function AlarmRow({ row }: { row: QueueRow }) {
  const selectObject = useSelectEventObject();
  const candidateId = row.candidateId;
  return (
    <button
      type="button"
      disabled={!candidateId}
      aria-label={rowAccessibleName(row)}
      onClick={() => candidateId && selectObject(candidateId)}
      className="relative flex h-8 shrink-0 items-center gap-2 border-b border-line-hairline pr-3 pl-4 text-left text-[12px] disabled:cursor-default"
    >
      <span aria-hidden className="absolute inset-y-0 left-0 w-[3px] bg-state-alarm" />
      <SeverityGlyph severity="alarm" size={14} />
      <span className="font-mono text-[11px] text-text-secondary">{eventStamp(row)}</span>
      <span className="min-w-0 flex-1 truncate font-semibold text-text-primary">{row.title}</span>
      <span className="font-mono text-[11px] text-text-primary">НОВОЕ</span>
      {row.isDemo ? <DemoTag /> : null}
    </button>
  );
}

export function SheetStatusLine() {
  const status = useApiStatus();
  return (
    <div className="flex min-h-9 shrink-0 flex-wrap items-center gap-x-3 gap-y-0.5 border-t border-line-hairline px-3 py-1.5 text-[11px] text-text-secondary">
      <ApiStatusLabel status={status} />
      <CoordinateText />
    </div>
  );
}

type SheetGripProps = {
  detent: SheetDetent;
  onCycle: () => void;
  onStep: (direction: 1 | -1) => void;
  drag: SheetDrag;
  children: ReactNode;
};

export function SheetGrip({ detent, onCycle, onStep, drag, children }: SheetGripProps) {
  const handleKeyDown = (event: KeyboardEvent<HTMLButtonElement>) => {
    if (event.key !== "ArrowUp" && event.key !== "ArrowDown") return;
    event.preventDefault();
    onStep(event.key === "ArrowUp" ? 1 : -1);
  };
  return (
    <button
      type="button"
      aria-label={`Высота панели: ${DETENT_LABEL[detent]}. Нажмите, чтобы изменить; стрелки вверх и вниз — по шагам`}
      onClick={() => {
        if (!drag.consumeClick()) onCycle();
      }}
      onKeyDown={handleKeyDown}
      {...drag.handlers}
      className="flex h-11 w-full touch-none flex-col items-stretch text-left select-none"
    >
      <span
        aria-hidden
        className="mx-auto mt-1.5 h-1 w-11 shrink-0 rounded-[2px] bg-line-control"
      />
      <span className="flex min-w-0 flex-1 items-center gap-2 pr-28 pl-3 text-[13px] font-medium text-text-primary">
        {children}
        {detent === "full" ? (
          <IconChevronDown size={14} className="shrink-0 text-text-secondary" />
        ) : (
          <IconChevronUp size={14} className="shrink-0 text-text-secondary" />
        )}
      </span>
    </button>
  );
}

export function ViewSwitch({
  view,
  canShowInspector,
  mode,
}: {
  view: "layers" | "inspector";
  canShowInspector: boolean;
  mode: WorkspaceModeId;
}) {
  const showSheet = useShellUiStore((state) => state.showSheet);
  if (view === "inspector") {
    return (
      <button
        type="button"
        onClick={() => showSheet("layers")}
        className="absolute top-1.5 right-2 flex h-10 items-center gap-1.5 rounded-[var(--radius-ctl)] border border-line-control bg-surface-raised px-2.5 text-[13px] text-text-primary"
      >
        <IconLayers size={16} />
        Слои
      </button>
    );
  }
  if (!canShowInspector) return null;
  return (
    <button
      type="button"
      onClick={() => showSheet("inspector")}
      className="absolute top-1.5 right-2 flex h-10 items-center rounded-[var(--radius-ctl)] border border-line-control bg-surface-raised px-2.5 text-[13px] text-text-primary"
    >
      {PANEL_TITLE[mode]} ›
    </button>
  );
}
