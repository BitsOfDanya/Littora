"use client";

import { useCallback, useMemo } from "react";
import {
  type EventSeverity,
  EVENT_PRIORITY,
  type QueueEvent,
  useQueueEventFixtures,
} from "@/data/events";
import { useSystemEventsStore } from "@/features/system/system-events";
import type { WorkspaceModeId } from "@/config/modes";
import { type Acknowledgement, useAckStore } from "@/state/ack-store";
import { useShellUiStore } from "@/state/shell-ui-store";
import { allowsInlineQueue, type ShellLayout } from "../layout/use-environment";

export type QueueRowState = "new" | "acknowledged" | "info";

export type QueueRow = QueueEvent & {
  isDemo: boolean;
  state: QueueRowState;
  acknowledgement: Acknowledgement | null;
};

export type QueueModel = {
  rows: readonly QueueRow[];
  newCount: number;
  worstNew: EventSeverity | null;
  newIncludesDemo: boolean;
  demoOrigin: "demo" | "none";
};

function rowState(event: QueueEvent, acknowledgement: Acknowledgement | null): QueueRowState {
  if (event.severity === "info") return "info";
  return acknowledgement ? "acknowledged" : "new";
}

function compareRows(a: QueueRow, b: QueueRow): number {
  if (a.state === "new" && b.state !== "new") return -1;
  if (b.state === "new" && a.state !== "new") return 1;
  if (a.state === "new" && EVENT_PRIORITY[a.severity] !== EVENT_PRIORITY[b.severity]) {
    return EVENT_PRIORITY[a.severity] - EVENT_PRIORITY[b.severity];
  }
  return Date.parse(b.occurredAt) - Date.parse(a.occurredAt);
}

export function useQueue(): QueueModel {
  const fixtures = useQueueEventFixtures();
  const systemEvents = useSystemEventsStore((state) => state.events);
  const acknowledgements = useAckStore((state) => state.acknowledgements);
  const demoEvents = fixtures.origin === "none" ? null : fixtures.data;

  return useMemo(() => {
    const tagged = [
      ...(demoEvents ?? []).map((event) => ({ event, isDemo: true })),
      ...systemEvents.map((event) => ({ event, isDemo: false })),
    ];
    const rows = tagged
      .map(({ event, isDemo }): QueueRow => {
        const acknowledgement = acknowledgements[event.id] ?? event.acknowledged;
        return { ...event, isDemo, acknowledgement, state: rowState(event, acknowledgement) };
      })
      .sort(compareRows);
    const fresh = rows.filter((row) => row.state === "new");
    const worstNew = fresh.reduce<EventSeverity | null>(
      (worst, row) =>
        worst === null || EVENT_PRIORITY[row.severity] < EVENT_PRIORITY[worst]
          ? row.severity
          : worst,
      null,
    );
    return {
      rows,
      newCount: fresh.length,
      worstNew,
      newIncludesDemo: fresh.some((row) => row.isDemo),
      demoOrigin: demoEvents ? "demo" : "none",
    };
  }, [demoEvents, systemEvents, acknowledgements]);
}

export function queueHasRail(mode: WorkspaceModeId | undefined): boolean {
  return mode !== undefined && mode !== "models";
}

function defaultQueueOpen(mode: WorkspaceModeId, layout: ShellLayout, newCount: number): boolean {
  return (mode === "monitor" || mode === "forecast") && allowsInlineQueue(layout) && newCount > 0;
}

export function useQueueOpen(
  mode: WorkspaceModeId | undefined,
  layout: ShellLayout,
  newCount: number,
): boolean {
  const override = useShellUiStore((state) => (mode ? state.queueOpenByMode[mode] : undefined));
  if (!mode || !queueHasRail(mode) || layout === "phone") return false;
  return override ?? defaultQueueOpen(mode, layout, newCount);
}

export function useQueueToggle(
  mode: WorkspaceModeId | undefined,
  layout: ShellLayout,
): (() => void) | null {
  const queue = useQueue();
  const open = useQueueOpen(mode, layout, queue.newCount);
  const setQueueOpen = useShellUiStore((state) => state.setQueueOpen);
  if (!mode || !queueHasRail(mode) || layout === "phone") return null;
  return () => setQueueOpen(mode, !open);
}

export function useCandidateEvents(candidateId: string | null): readonly QueueRow[] {
  const { rows } = useQueue();
  return useMemo(
    () => (candidateId ? rows.filter((row) => row.candidateId === candidateId) : []),
    [rows, candidateId],
  );
}

export function useUnacknowledgedCandidateIds(): readonly string[] {
  const { rows } = useQueue();
  return useMemo(
    () => [
      ...new Set(
        rows.flatMap((row) => (row.state === "new" && row.candidateId ? [row.candidateId] : [])),
      ),
    ],
    [rows],
  );
}

export function useAcknowledgeCandidate(): (candidateId: string) => void {
  const { rows } = useQueue();
  const acknowledge = useAckStore((state) => state.acknowledge);
  return useCallback(
    (candidateId: string) =>
      acknowledge(
        rows
          .filter((row) => row.candidateId === candidateId && row.state === "new")
          .map((row) => row.id),
      ),
    [rows, acknowledge],
  );
}
