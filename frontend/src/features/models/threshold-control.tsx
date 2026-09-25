"use client";

import { type CSSProperties, useId } from "react";
import type { ModelEvaluation } from "@/data/models";
import { Button } from "@/ui/button";
import { PR_COPY } from "./copy";
import { DASH, formatShare } from "./format";
import { f1Score, pointAtThreshold, snapThreshold, thresholdRange } from "./pr-math";
import styles from "./report.module.css";

type ThresholdControlProps = {
  model: ModelEvaluation | null;
  threshold: number | null;
  onThreshold: (value: number) => void;
};

export function ThresholdControl({ model, threshold, onThreshold }: ThresholdControlProps) {
  const inputId = useId();
  const curve = model?.prCurve ?? null;
  const [min, max] = curve ? thresholdRange(curve) : [0, 1];
  const value = threshold ?? 0.5;
  const point = curve ? pointAtThreshold(curve, value) : null;
  const fill = `${(((value - min) / (max - min || 1)) * 100).toFixed(1)}%`;
  const changed =
    model !== null && threshold !== null && Math.abs(threshold - model.threshold) > 0.001;
  const readout = point
    ? `P ${formatShare(point.precision)} · R ${formatShare(point.recall)} · F1 ${formatShare(f1Score(point.precision, point.recall))}`
    : `P ${DASH} · R ${DASH}`;

  return (
    <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 pl-[44px] max-md:pl-0">
      <label htmlFor={inputId} className="text-[12px] text-text-secondary">
        {PR_COPY.threshold}
      </label>
      <input
        id={inputId}
        type="range"
        min={min}
        max={max}
        step={0.01}
        value={value}
        disabled={!curve}
        onChange={(event) => onThreshold(snapThreshold(Number(event.target.value)))}
        aria-valuetext={
          point
            ? `порог ${formatShare(value)}: точность ${formatShare(point.precision)}, полнота ${formatShare(point.recall)}`
            : "нет данных"
        }
        style={{ "--fill": fill } as CSSProperties}
        className={`min-w-[140px] flex-1 ${styles.range}`}
      />
      <output htmlFor={inputId} className="w-9 font-mono text-[13px] font-medium text-text-primary">
        {curve ? formatShare(value) : DASH}
      </output>
      <output
        htmlFor={inputId}
        aria-live="polite"
        className="basis-full font-mono text-[12px] text-text-secondary sm:basis-auto"
      >
        {readout}
      </output>
      {changed && model ? (
        <Button
          size="sm"
          onClick={() => onThreshold(model.threshold)}
          title="Вернуть рабочий порог модели"
        >
          {PR_COPY.reset} {formatShare(model.threshold)}
        </Button>
      ) : null}
    </div>
  );
}

export function PrLegend({ model }: { model: ModelEvaluation | null }) {
  return (
    <ul className="mt-3 flex flex-wrap gap-x-4 gap-y-1 pl-[44px] text-[12px] leading-4 text-text-tertiary max-md:pl-0">
      <li className="inline-flex items-center gap-1.5">
        <svg width={18} height={8} aria-hidden>
          <path d="M1 4H17" strokeWidth={2} className="stroke-text-primary" />
        </svg>
        {PR_COPY.legendCurve}
      </li>
      <li className="inline-flex items-center gap-1.5">
        <svg width={10} height={10} aria-hidden>
          <circle
            cx={5}
            cy={5}
            r={3.5}
            strokeWidth={1.5}
            className="fill-surface-panel stroke-text-primary"
          />
        </svg>
        {PR_COPY.legendOperating}
        {model ? <span className="font-mono">{formatShare(model.threshold)}</span> : null}
      </li>
      <li className="inline-flex items-center gap-1.5">
        <svg width={10} height={10} aria-hidden>
          <circle cx={5} cy={5} r={4} className="fill-accent-selection" />
        </svg>
        {PR_COPY.legendChosen}
      </li>
      <li className="inline-flex items-center gap-1.5">
        <svg width={18} height={8} aria-hidden>
          <path
            d="M1 4H17"
            strokeDasharray="1 3"
            strokeLinecap="round"
            className="stroke-text-tertiary"
          />
        </svg>
        {PR_COPY.legendIso}
      </li>
    </ul>
  );
}
