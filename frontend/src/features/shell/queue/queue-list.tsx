"use client";

import { useEffect, useRef } from "react";
import { useAckStore } from "@/state/ack-store";
import { cn } from "@/ui/cn";
import { DemoTag } from "@/ui/demo-mark";
import { SeverityGlyph } from "@/ui/indicators";
import { usePrefersReducedMotion } from "../layout/use-environment";
import {
  acknowledgementLine,
  eventStamp,
  rowAccessibleName,
  SEVERITY_BAR,
  STATE_WORD,
} from "./queue-copy";
import type { QueueRow } from "./use-queue";
import { useSelectEventObject } from "./use-select-event-object";

const HIGHLIGHT_MS = 240;

function RowSummary({ row }: { row: QueueRow }) {
  return (
    <>
      <SeverityGlyph
        severity={row.severity}
        acknowledged={row.state !== "new"}
        size={14}
        className="mt-px shrink-0"
      />
      <span className="w-10 shrink-0 font-mono text-[11px] leading-4 text-text-secondary">
        {eventStamp(row)}
      </span>
      <span
        title={acknowledgementLine(row) ?? undefined}
        className={cn(
          "min-w-0 flex-1 truncate text-[12px] leading-4 text-text-primary group-focus-within/row:whitespace-normal group-hover/row:whitespace-normal",
          row.state === "new" ? "font-semibold" : "text-text-secondary",
        )}
      >
        {row.title}
      </span>
    </>
  );
}

function StateCell({ row }: { row: QueueRow }) {
  const acknowledge = useAckStore((state) => state.acknowledge);
  const word = (
    <span
      className={cn(
        "font-mono text-[11px] leading-5 tracking-[0.04em]",
        row.state === "new"
          ? "text-text-primary group-focus-within/row:opacity-0 group-hover/row:opacity-0"
          : "text-text-tertiary",
      )}
    >
      {STATE_WORD[row.state]}
    </span>
  );
  if (row.state !== "new")
    return <span className="flex w-[46px] shrink-0 items-center">{word}</span>;
  return (
    <span className="relative flex w-[46px] shrink-0 items-center">
      {word}
      <button
        type="button"
        aria-label={`Квитировать: ${row.title}`}
        title="Квитировать · A"
        onClick={() => acknowledge([row.id])}
        className="absolute inset-y-0 left-0 inline-flex h-5 items-center rounded-[var(--radius-ctl)] border border-line-control bg-surface-raised px-1 font-mono text-[11px] text-text-primary opacity-0 group-focus-within/row:opacity-100 group-hover/row:opacity-100 hover:border-line-strong focus-visible:opacity-100"
      >
        Квит.
      </button>
    </span>
  );
}

function QueueListRow({
  row,
  onSelect,
}: {
  row: QueueRow;
  onSelect: (candidateId: string) => void;
}) {
  const candidateId = row.candidateId;
  const summaryClass = "flex min-w-0 flex-1 items-start gap-2 py-[5px] text-left";
  return (
    <li
      data-event-id={row.id}
      className="group/row relative flex min-h-[26px] items-start gap-2 border-b border-line-hairline pr-2 pl-3 hover:bg-surface-raised"
    >
      {row.state === "new" ? (
        <span
          aria-hidden
          className={cn("absolute inset-y-0 left-0 w-[3px]", SEVERITY_BAR[row.severity])}
        />
      ) : null}
      {candidateId ? (
        <button
          type="button"
          aria-label={`${rowAccessibleName(row)}. Открыть объект ${candidateId}`}
          onClick={() => onSelect(candidateId)}
          className={summaryClass}
        >
          <RowSummary row={row} />
        </button>
      ) : (
        <div tabIndex={0} aria-label={rowAccessibleName(row)} className={summaryClass}>
          <RowSummary row={row} />
        </div>
      )}
      <span className="flex shrink-0 items-center gap-1.5 py-[3px]">
        <StateCell row={row} />
        {row.isDemo ? <DemoTag /> : null}
      </span>
    </li>
  );
}

function useArrivalHighlight(rows: readonly QueueRow[]) {
  const listRef = useRef<HTMLUListElement>(null);
  const seenRef = useRef<Set<string> | null>(null);
  const reducedMotion = usePrefersReducedMotion();

  useEffect(() => {
    const list = listRef.current;
    const seen = seenRef.current;
    const ids = rows.map((row) => row.id);
    seenRef.current = new Set([...(seen ?? []), ...ids]);
    if (!seen || !list || reducedMotion) return;
    for (const row of rows) {
      if (seen.has(row.id) || row.severity === "info") continue;
      const element = list.querySelector<HTMLElement>(`[data-event-id="${CSS.escape(row.id)}"]`);
      element?.animate(
        [
          { backgroundColor: `var(--state-${row.severity}-wash)` },
          { backgroundColor: "transparent" },
        ],
        { duration: HIGHLIGHT_MS, easing: "cubic-bezier(.2,0,.38,.9)" },
      );
    }
  }, [rows, reducedMotion]);

  return listRef;
}

export function QueueList({
  rows,
  onSelected,
}: {
  rows: readonly QueueRow[];
  onSelected?: () => void;
}) {
  const selectObject = useSelectEventObject();
  const listRef = useArrivalHighlight(rows);
  const onSelect = (candidateId: string) => {
    selectObject(candidateId);
    onSelected?.();
  };
  return (
    <ul ref={listRef} aria-label="События" className="min-h-0 flex-1 overflow-y-auto">
      {rows.map((row) => (
        <QueueListRow key={row.id} row={row} onSelect={onSelect} />
      ))}
    </ul>
  );
}

export function QueueEmpty() {
  return (
    <p className="px-3 py-2 text-[12px] leading-4 text-text-secondary">
      Очередь пуста. События появятся после подключения обнаружения и прогноза
      <span className="mt-0.5 block font-mono text-[11px] text-text-tertiary">
        debris_detection · drift_forecast — planned
      </span>
    </p>
  );
}
