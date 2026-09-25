"use client";

import Link from "next/link";
import { WORKSPACE_MODES } from "@/config/modes";
import { useSurveyPlanEntry, useSurveyPlanStore } from "@/features/monitor/survey-plan-store";
import { useHotkey } from "@/features/shell/hotkeys";
import { modeHref, useViewQuery } from "@/features/shell/orientation/modes";
import { useStatusHintStore } from "@/features/shell/status-hint-store";
import { useShellUiStore } from "@/state/shell-ui-store";
import { Button, buttonClasses } from "@/ui/button";
import { IconArrowRight, IconFlag } from "@/ui/icons";
import { Kbd } from "@/ui/kbd";
import { AcknowledgeButton } from "../acknowledge-button";

const FORECAST_MODE = WORKSPACE_MODES.find((mode) => mode.id === "forecast") ?? WORKSPACE_MODES[2];

function PlanButton({ candidateId }: { candidateId: string }) {
  const entry = useSurveyPlanEntry(candidateId);
  const add = useSurveyPlanStore((state) => state.add);
  const toggle = useSurveyPlanStore((state) => state.toggle);
  const setHint = useStatusHintStore((state) => state.setHint);
  const modalOpen = useShellUiStore((state) => state.shortcutSheetOpen);

  useHotkey(
    "KeyS",
    () => {
      if (!add(candidateId)) setHint(`${candidateId} уже в плане обследования`);
      else setHint(`${candidateId} добавлен в план обследования`);
    },
    { enabled: !modalOpen },
  );

  return (
    <Button
      size="lg"
      aria-pressed={Boolean(entry)}
      aria-keyshortcuts="S"
      title={entry ? "Убрать из плана обследования" : "Добавить в план обследования · S"}
      onClick={() => toggle(candidateId)}
      className={entry ? "border-accent-selection text-accent-selection" : undefined}
    >
      <IconFlag size={14} />
      {entry ? "В плане" : "В план"}
      {entry ? null : <Kbd>S</Kbd>}
    </Button>
  );
}

export function DossierFooter({ candidateId }: { candidateId: string }) {
  const query = useViewQuery();
  return (
    <div className="@container flex w-full items-center gap-2">
      <AcknowledgeButton candidateId={candidateId} className="min-w-0" />
      <PlanButton candidateId={candidateId} />
      <Link
        href={modeHref(FORECAST_MODE, query)}
        title="Прогноз дрейфа для этого пятна · режим 3"
        className={buttonClasses("default", "lg")}
      >
        Прогноз<span className="hidden @[380px]:inline"> дрейфа</span>
        <IconArrowRight size={14} />
      </Link>
    </div>
  );
}
