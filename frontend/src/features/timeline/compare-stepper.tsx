"use client";

import type { SceneSummary } from "@/domain/scene";
import { cn } from "@/ui/cn";
import { DemoTag } from "@/ui/demo-mark";
import { SeverityGlyph } from "@/ui/indicators";
import { StepperStrip } from "@/ui/stepper-strip";
import { type CompareSide, dayMonth, isUsable, MOSAIC_YEARS } from "./compare-model";
import { useCompareViewStore } from "./compare-view-store";
import { useCompareActions, useCompareData } from "./use-compare";

function SideChip({
  side,
  scene,
  active,
  onSelect,
}: {
  side: CompareSide;
  scene: SceneSummary | undefined;
  active: boolean;
  onSelect: () => void;
}) {
  const letter = side === "a" ? "A" : "B";
  return (
    <button
      type="button"
      aria-pressed={active}
      aria-label={`Шагать датой ${letter}`}
      disabled={!scene}
      onClick={onSelect}
      className={cn(
        "flex h-10 items-center gap-1.5 rounded-[var(--radius-ctl)] border px-2 font-mono text-[13px] whitespace-nowrap",
        active
          ? "border-primary-fill bg-surface-raised font-semibold text-text-primary shadow-[inset_0_-3px_0_var(--text-primary)]"
          : "border-line-control text-text-secondary",
      )}
    >
      <span className="grid size-[18px] place-items-center bg-primary-fill font-sans text-[11px] font-bold text-primary-text">
        {letter}
      </span>
      {scene ? dayMonth(scene.acquiredAt) : `мозаика ${MOSAIC_YEARS[side]}`}
      {scene && !isUsable(scene) ? <SeverityGlyph severity="caution" size={12} /> : null}
    </button>
  );
}

export function CompareStepper() {
  const { scenes, pair, isDemo } = useCompareData();
  const actions = useCompareActions(scenes, pair);
  const activeSide = useCompareViewStore((state) => state.activeSide);
  const setActiveSide = useCompareViewStore((state) => state.setActiveSide);
  const letter = activeSide === "a" ? "A" : "B";

  return (
    <StepperStrip
      label="Даты сравнения A и B"
      previousLabel={`Дата ${letter}: предыдущий пролёт`}
      nextLabel={`Дата ${letter}: следующий пролёт`}
      canStepBack={Boolean(pair) && actions.canStep(activeSide, -1)}
      canStepForward={Boolean(pair) && actions.canStep(activeSide, 1)}
      onStep={(direction) => actions.step(activeSide, direction)}
    >
      <SideChip
        side="a"
        scene={pair?.a}
        active={Boolean(pair) && activeSide === "a"}
        onSelect={() => setActiveSide("a")}
      />
      <span aria-hidden className="text-text-tertiary">
        →
      </span>
      <SideChip
        side="b"
        scene={pair?.b}
        active={Boolean(pair) && activeSide === "b"}
        onSelect={() => setActiveSide("b")}
      />
      {isDemo ? <DemoTag /> : null}
    </StepperStrip>
  );
}
