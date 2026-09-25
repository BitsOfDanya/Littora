import type { ReactNode } from "react";
import { IconButton } from "./button";
import { IconChevronLeft, IconChevronRight } from "./icons";

type StepperStripProps = {
  label: string;
  previousLabel: string;
  nextLabel: string;
  canStepBack: boolean;
  canStepForward: boolean;
  onStep: (direction: 1 | -1) => void;
  children: ReactNode;
};

export function StepperStrip({
  label,
  previousLabel,
  nextLabel,
  canStepBack,
  canStepForward,
  onStep,
  children,
}: StepperStripProps) {
  return (
    <div role="group" aria-label={label} className="flex h-full items-center gap-2 px-2">
      <IconButton
        label={previousLabel}
        size="lg"
        disabled={!canStepBack}
        onClick={() => onStep(-1)}
      >
        <IconChevronLeft size={20} />
      </IconButton>
      <div
        aria-live="polite"
        className="flex min-w-0 flex-1 flex-wrap items-center justify-center gap-x-2 gap-y-0.5 text-center"
      >
        {children}
      </div>
      <IconButton label={nextLabel} size="lg" disabled={!canStepForward} onClick={() => onStep(1)}>
        <IconChevronRight size={20} />
      </IconButton>
    </div>
  );
}
