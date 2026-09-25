"use client";

import type { SceneSummary } from "@/domain/scene";
import { formatPercent } from "@/lib/format/numbers";
import { IconButton } from "@/ui/button";
import { cn } from "@/ui/cn";
import { IconChevronLeft, IconChevronRight } from "@/ui/icons";
import { SeverityGlyph } from "@/ui/indicators";
import { sceneAccessibleName } from "./compare-format";
import { type CompareSide, dayMonth, isUsable, MOSAIC_YEARS } from "./compare-model";
import type { CompareActions } from "./use-compare";

export function SideLetter({ side, className }: { side: CompareSide; className?: string }) {
  return (
    <span
      aria-hidden
      className={cn(
        "grid size-[18px] shrink-0 place-items-center bg-primary-fill font-sans text-[11px] font-bold text-primary-text",
        className,
      )}
    >
      {side === "a" ? "A" : "B"}
    </span>
  );
}

export function CloudMark({ scene }: { scene: SceneSummary }) {
  if (isUsable(scene))
    return <span className="text-text-secondary">{formatPercent(scene.cloudCover)}</span>;
  return (
    <span className="inline-flex items-center gap-1 text-state-caution">
      <SeverityGlyph severity="caution" size={12} />
      {formatPercent(scene.cloudCover)}
    </span>
  );
}

type PickerProps = {
  side: CompareSide;
  scene: SceneSummary;
  actions: CompareActions;
};

function Picker({ side, scene, actions }: PickerProps) {
  const letter = side === "a" ? "A" : "B";
  return (
    <div
      role="group"
      aria-label={sceneAccessibleName(letter, scene)}
      className="flex items-center gap-1.5"
    >
      <SideLetter side={side} />
      <IconButton
        label={`Дата ${letter}: предыдущий пролёт`}
        shortcut={side === "b" ? "[" : undefined}
        size="sm"
        disabled={!actions.canStep(side, -1)}
        onClick={() => actions.step(side, -1)}
      >
        <IconChevronLeft />
      </IconButton>
      <span className="flex min-w-[168px] items-center gap-1.5 font-mono text-[13px] text-text-primary">
        <span className="font-semibold">{dayMonth(scene.acquiredAt)}</span>
        <span className="text-text-tertiary">·</span>
        <span>{scene.platform}</span>
        <span className="text-text-tertiary">·</span>
        <CloudMark scene={scene} />
      </span>
      <IconButton
        label={`Дата ${letter}: следующий пролёт`}
        shortcut={side === "b" ? "]" : undefined}
        size="sm"
        disabled={!actions.canStep(side, 1)}
        onClick={() => actions.step(side, 1)}
      >
        <IconChevronRight />
      </IconButton>
    </div>
  );
}

export function ComparePickers({
  a,
  b,
  actions,
}: {
  a: SceneSummary;
  b: SceneSummary;
  actions: CompareActions;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <Picker side="a" scene={a} actions={actions} />
      <Picker side="b" scene={b} actions={actions} />
    </div>
  );
}

export function MosaicPair() {
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 font-mono text-[13px]">
      {(["a", "b"] as const).map((side) => (
        <span key={side} className="inline-flex items-center gap-1.5">
          <SideLetter side={side} />
          мозаика {MOSAIC_YEARS[side]}
        </span>
      ))}
    </div>
  );
}
