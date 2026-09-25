"use client";

import {
  type KeyboardEvent,
  type RefObject,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import type { DebrisCandidate } from "@/domain/detection";
import { useStatusHintStore } from "@/features/shell/status-hint-store";
import { formatNumber, formatSigned } from "@/lib/format/numbers";
import { useCartoucheStore } from "@/state/cartouche-store";
import { useWorkspaceStore } from "@/state/workspace-store";
import { cn } from "@/ui/cn";
import { CONFIDENCE_WORD, ConfidenceGlyph, PRIORITY_WORD, PriorityBars } from "@/ui/indicators";
import { orderByPriority } from "./object-order";
import { useSelectObject } from "./use-select-object";

export type TableDensity = "compact" | "touch";

const HEADER_CELL =
  "sticky top-0 z-[1] h-7 border-b border-line-hairline bg-surface-panel px-1 text-left text-[11px] font-semibold whitespace-nowrap text-text-tertiary";
const CELL = "px-1 whitespace-nowrap";

function percentValue(ratio: number): string {
  const percent = Math.round(ratio * 1000) / 10;
  return formatNumber(percent, Number.isInteger(percent) ? 0 : 1);
}

function deltaValue(candidate: DebrisCandidate): string {
  return candidate.change ? formatSigned(Math.round(candidate.change.areaDeltaRatio * 100)) : "—";
}

function rowLabel(candidate: DebrisCandidate): string {
  const delta = candidate.change ? `, изменение площади ${deltaValue(candidate)} %` : "";
  return `${candidate.id}, приоритет ${PRIORITY_WORD[candidate.priority].toLowerCase()}, уверенность ${CONFIDENCE_WORD[candidate.confidence.class]} ${formatNumber(candidate.confidence.score, 2)}, покрытие ${percentValue(candidate.coverage.value)} %${delta}`;
}

type ObjectRowProps = {
  candidate: DebrisCandidate;
  selected: boolean;
  active: boolean;
  density: TableDensity;
  registerRef: (id: string, element: HTMLTableRowElement | null) => void;
  onSelect: () => void;
  onFocus: () => void;
};

function ObjectRow({
  candidate,
  selected,
  active,
  density,
  registerRef,
  onSelect,
  onFocus,
}: ObjectRowProps) {
  const setHint = useStatusHintStore((state) => state.setHint);
  return (
    <tr
      ref={(element) => registerRef(candidate.id, element)}
      tabIndex={active ? 0 : -1}
      aria-selected={selected}
      aria-label={rowLabel(candidate)}
      onClick={onSelect}
      onFocus={onFocus}
      onMouseEnter={() => setHint(`${candidate.id} — щелчок: открыть досье`)}
      onMouseLeave={() => setHint(null)}
      className={cn(
        "cursor-pointer text-[12px] text-text-primary transition-colors duration-[var(--t-2)] focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-focus-ring",
        density === "touch" ? "h-10" : "h-7",
        selected
          ? "bg-accent-selection-wash [&>td:first-child]:shadow-[inset_3px_0_0_var(--accent-selection)]"
          : "hover:bg-surface-raised",
      )}
    >
      <td className={cn(CELL, "pl-2")}>
        <PriorityBars priority={candidate.priority} />
      </td>
      <td className={cn(CELL, "font-mono font-medium", selected && "text-accent-selection")}>
        {candidate.id}
      </td>
      <td className={CELL}>
        <ConfidenceGlyph
          confidence={candidate.confidence.class}
          score={candidate.confidence.score}
          withWord={false}
        />
      </td>
      <td className={cn(CELL, "text-right font-mono")}>{percentValue(candidate.coverage.value)}</td>
      <td
        className={cn(CELL, "pr-2 text-right font-mono", !candidate.change && "text-text-tertiary")}
      >
        {deltaValue(candidate)}
      </td>
    </tr>
  );
}

type RowRefs = RefObject<Map<string, HTMLTableRowElement>>;

function useTableFocusRequest(activeId: string | null, rows: RowRefs) {
  const pending = useCartoucheStore((state) => state.tableFocusPending);
  const consume = useCartoucheStore((state) => state.consumeTableFocus);

  useEffect(() => {
    if (!pending || !activeId) return;
    rows.current.get(activeId)?.focus();
    consume();
  }, [pending, activeId, rows, consume]);
}

export function ObjectTable({
  candidates,
  density = "compact",
}: {
  candidates: readonly DebrisCandidate[];
  density?: TableDensity;
}) {
  const ordered = useMemo(() => orderByPriority(candidates), [candidates]);
  const selectedId = useWorkspaceStore((state) => state.selectedCandidateId);
  const selectObject = useSelectObject();
  const [focusedId, setFocusedId] = useState<string | null>(null);
  const rowsRef = useRef(new Map<string, HTMLTableRowElement>());
  const known = (id: string | null) =>
    id && ordered.some((candidate) => candidate.id === id) ? id : null;
  const activeId = known(focusedId) ?? known(selectedId) ?? ordered[0]?.id ?? null;

  useTableFocusRequest(activeId, rowsRef);

  useEffect(() => {
    if (selectedId) rowsRef.current.get(selectedId)?.scrollIntoView({ block: "nearest" });
  }, [selectedId]);

  const registerRef = useCallback((id: string, element: HTMLTableRowElement | null) => {
    if (element) rowsRef.current.set(id, element);
    else rowsRef.current.delete(id);
  }, []);

  const moveFocus = (target: DebrisCandidate | undefined) => {
    if (!target) return;
    setFocusedId(target.id);
    rowsRef.current.get(target.id)?.focus();
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLTableSectionElement>) => {
    const index = ordered.findIndex((candidate) => candidate.id === activeId);
    const current = ordered[index];
    if (event.key === "ArrowDown") moveFocus(ordered[Math.min(index + 1, ordered.length - 1)]);
    else if (event.key === "ArrowUp") moveFocus(ordered[Math.max(index - 1, 0)]);
    else if (event.key === "Home") moveFocus(ordered[0]);
    else if (event.key === "End") moveFocus(ordered.at(-1));
    else if (event.key === "Enter" && current) selectObject(current);
    else return;
    event.preventDefault();
  };

  return (
    <table
      role="grid"
      aria-label="Объекты: пятна-кандидаты по приоритету"
      aria-readonly
      className="w-full border-collapse"
    >
      <thead>
        <tr>
          <th scope="col" className={cn(HEADER_CELL, "pl-2")} title="Приоритет проверки">
            П
          </th>
          <th scope="col" className={HEADER_CELL}>
            Объект
          </th>
          <th scope="col" className={HEADER_CELL} title="Уверенность модели: класс линией и балл">
            Увер.
          </th>
          <th
            scope="col"
            className={cn(HEADER_CELL, "text-right")}
            title="Доля покрытия пикселя, %"
          >
            Покр., %
          </th>
          <th
            scope="col"
            className={cn(HEADER_CELL, "pr-2 text-right")}
            title="Изменение площади к предыдущему пролёту, %"
          >
            Δ, %
          </th>
        </tr>
      </thead>
      <tbody onKeyDown={handleKeyDown}>
        {ordered.map((candidate) => (
          <ObjectRow
            key={candidate.id}
            candidate={candidate}
            selected={candidate.id === selectedId}
            active={candidate.id === activeId}
            density={density}
            registerRef={registerRef}
            onSelect={() => selectObject(candidate)}
            onFocus={() => setFocusedId(candidate.id)}
          />
        ))}
      </tbody>
    </table>
  );
}
