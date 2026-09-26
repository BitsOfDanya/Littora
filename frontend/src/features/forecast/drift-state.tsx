"use client";

import Link from "next/link";
import { WORKSPACE_MODES } from "@/config/modes";
import type { DriftState } from "@/data/drift";
import { modeHref, useViewQuery } from "@/features/shell/orientation/modes";
import { Button, buttonClasses } from "@/ui/button";
import { cn } from "@/ui/cn";
import { driftStateCopy, SCENARIO_NOTE, upperFirst } from "./forecast-copy";

const MONITOR_MODE = WORKSPACE_MODES[0];

export function ScenarioTag({ className }: { className?: string }) {
  return (
    <span
      title={upperFirst(SCENARIO_NOTE)}
      className={cn(
        "inline-flex h-[18px] shrink-0 items-center rounded-[var(--radius-ctl)] border border-line-control px-1 font-mono text-[11px] leading-none text-text-secondary",
        className,
      )}
    >
      сценарий
    </span>
  );
}

export function DriftStateAction({
  state,
  size = "md",
}: {
  state: DriftState;
  size?: "sm" | "md";
}) {
  const viewQuery = useViewQuery();
  switch (state.status) {
    case "absent":
      return (
        <Button variant="primary" size={size} onClick={state.compute}>
          Рассчитать дрейф
        </Button>
      );
    case "computing":
      return (
        <Button variant="primary" size={size} busy disabled>
          Считаем…
        </Button>
      );
    case "failed":
    case "unavailable":
      return (
        <Button size={size} onClick={state.retry}>
          Повторить
        </Button>
      );
    case "no-analysis":
    case "no-zones":
      return (
        <Link href={modeHref(MONITOR_MODE, viewQuery)} className={buttonClasses("default", size)}>
          Открыть мониторинг
        </Link>
      );
    default:
      return null;
  }
}

export function DriftStatePanel({ state }: { state: DriftState }) {
  const copy = driftStateCopy(state);
  if (!copy) return null;
  return (
    <section className="flex flex-col gap-2 p-4" aria-live="polite">
      <h3 className="text-[13px] font-semibold text-text-primary">{copy.title}</h3>
      <p
        className={cn(
          "text-[13px] text-text-secondary",
          state.status === "failed" && "text-state-alarm",
        )}
      >
        {copy.detail}
      </p>
      <p className="text-[11px] leading-4 text-text-tertiary">Результат — {SCENARIO_NOTE}.</p>
      <div className="pt-1">
        <DriftStateAction state={state} />
      </div>
    </section>
  );
}
