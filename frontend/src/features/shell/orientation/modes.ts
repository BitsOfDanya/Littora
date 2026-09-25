"use client";

import type { Route } from "next";
import { usePathname } from "next/navigation";
import {
  findModeByPathname,
  WORKSPACE_MODES,
  type WorkspaceMode,
  type WorkspaceModeId,
} from "@/config/modes";
import { useWorkspaceStore } from "@/state/workspace-store";

export const MODE_PURPOSE: Record<WorkspaceModeId, string> = {
  monitor: "Восприятие: что видно на снимке сейчас",
  timeline: "Понимание: как менялось между пролётами",
  forecast: "Проекция: куда унесёт через 6–72 ч",
  survey: "Действие: что и зачем проверить",
  models: "Доверие: насколько точны модели",
};

export const MODE_DIGIT_CODES = ["Digit1", "Digit2", "Digit3", "Digit4", "Digit5"] as const;

export function useActiveMode(): WorkspaceMode | undefined {
  return findModeByPathname(usePathname());
}

export function modeForDigitCode(code: string): WorkspaceMode | undefined {
  const index = MODE_DIGIT_CODES.indexOf(code as (typeof MODE_DIGIT_CODES)[number]);
  return index === -1 ? undefined : WORKSPACE_MODES[index];
}

export function viewQuery(aoiId: string, selectedId: string | null): string {
  const params = new URLSearchParams({ aoi: aoiId });
  if (selectedId) params.set("sel", selectedId);
  return params.toString();
}

export function modeHref(mode: WorkspaceMode, query: string): Route {
  return `${mode.href}?${query}` as Route;
}

export function useViewQuery(): string {
  const aoiId = useWorkspaceStore((state) => state.aoiId);
  const selectedId = useWorkspaceStore((state) => state.selectedCandidateId);
  return viewQuery(aoiId, selectedId);
}
