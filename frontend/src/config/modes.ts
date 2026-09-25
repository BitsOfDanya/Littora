import type { Route } from "next";
import type { CapabilityKey } from "@/lib/api/system";

export type WorkspaceModeId = "monitor" | "timeline" | "forecast" | "survey" | "models";

export type WorkspaceMode = {
  id: WorkspaceModeId;
  href: Route;
  hotkey: string;
  label: string;
  shortLabel: string;
  summary: string;
  capabilities: readonly CapabilityKey[];
};

export const WORKSPACE_MODES = [
  {
    id: "monitor",
    href: "/monitor",
    hotkey: "1",
    label: "Мониторинг",
    shortLabel: "Карта",
    summary: "Сцены, слои и выявленные скопления на выбранной акватории",
    capabilities: ["scene_catalog", "debris_detection", "segmentation", "coverage_estimation"],
  },
  {
    id: "timeline",
    href: "/timeline",
    hotkey: "2",
    label: "Динамика",
    shortLabel: "Время",
    summary: "Наблюдения по датам и сравнение двух снимков",
    capabilities: ["scene_catalog", "change_tracking"],
  },
  {
    id: "forecast",
    href: "/forecast",
    hotkey: "3",
    label: "Прогноз",
    shortLabel: "Дрейф",
    summary: "Дрейф скоплений по течениям и ветру на 6–72 часа",
    capabilities: ["drift_forecast"],
  },
  {
    id: "survey",
    href: "/survey",
    hotkey: "4",
    label: "Обследование",
    shortLabel: "Цели",
    summary: "Участки, которые стоит проверить, и почему",
    capabilities: ["survey_planning"],
  },
  {
    id: "models",
    href: "/models",
    hotkey: "5",
    label: "Модели",
    shortLabel: "Модели",
    summary: "Модели, метрики качества и датасеты",
    capabilities: ["model_evaluation"],
  },
] as const satisfies readonly WorkspaceMode[];

export const DEFAULT_MODE_HREF: Route = WORKSPACE_MODES[0].href;

export function findModeByPathname(pathname: string): WorkspaceMode | undefined {
  return WORKSPACE_MODES.find(
    (mode) => pathname === mode.href || pathname.startsWith(`${mode.href}/`),
  );
}
