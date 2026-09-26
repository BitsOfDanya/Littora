"use client";

import type { LayerGroupId } from "@/config/layers";
import { useApiMeta } from "@/features/system/use-capabilities";
import type { CapabilityKey } from "@/lib/api/system";
import { useWorkspaceStore } from "@/state/workspace-store";
import { Button } from "@/ui/button";
import { IconSocket } from "@/ui/icons";
import { PlannedState, PlannedTag } from "@/ui/planned";

type GroupPlan = { title: string; capability: CapabilityKey; body: string; requirement?: string };

const GROUP_PLANS: Partial<Record<LayerGroupId, GroupPlan>> = {
  results: {
    title: "Детекция мусора — не подключено",
    capability: "debris_detection",
    body: "Контуры кандидатов, доля покрытия, уверенность и неопределённость появятся здесь как слои.",
    requirement: "сцена Sentinel-2 L2A и модель детекции.",
  },
  forecast: {
    title: "Прогноз дрейфа — не подключено",
    capability: "drift_forecast",
    body: "Частицы течений, облака вероятности на +6…+72\u202Fч и обратный дрейф к вероятному источнику.",
    requirement: "зоны детектора из анализа района; ветер, волны и течения Open-Meteo.",
  },
  survey: {
    title: "Планирование обследований — не подключено",
    capability: "survey_planning",
    body: "Ранжированный список участков для проверки с судна или БПЛА: зачем, насколько срочно и что это даст.",
  },
};

export function DemoAction() {
  const demoFixtures = useWorkspaceStore((state) => state.demoFixtures);
  const setDemoFixtures = useWorkspaceStore((state) => state.setDemoFixtures);
  if (demoFixtures)
    return <p className="text-[12px] text-text-tertiary">Для этого района демо-данных нет.</p>;
  return (
    <Button onClick={() => setDemoFixtures(true)} title="Включить демо-фикстуры · D">
      Показать на демо-данных
    </Button>
  );
}

export function PlannedGroupNote({ group }: { group: LayerGroupId }) {
  const meta = useApiMeta();
  const plan = GROUP_PLANS[group];
  if (!plan) return null;
  const status = meta.isPending ? "loading" : meta.isError ? "error" : "planned";
  return (
    <PlannedState
      title={plan.title}
      capability={plan.capability}
      status={status}
      requirement={plan.requirement}
      className="my-1 p-3"
      action={
        status === "error" ? (
          <Button onClick={() => void meta.refetch()}>Повторить</Button>
        ) : (
          <DemoAction />
        )
      }
    >
      {plan.body}
    </PlannedState>
  );
}

export function PlannedLine({
  capability,
  children,
}: {
  capability: CapabilityKey;
  children: string;
}) {
  return (
    <div className="flex items-start gap-2 py-1">
      <IconSocket size={14} className="mt-px shrink-0 text-text-tertiary" />
      <span className="min-w-0 flex-1 text-[12px] leading-4 text-text-secondary">{children}</span>
      <PlannedTag capability={capability} />
    </div>
  );
}
