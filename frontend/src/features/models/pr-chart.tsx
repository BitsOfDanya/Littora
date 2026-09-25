"use client";

import { type PointerEvent, useRef } from "react";
import type { ModelEvaluation } from "@/data/models";
import type { PrCurvePoint } from "@/domain/model";
import { PR_COPY } from "./copy";
import { formatShare } from "./format";
import {
  ISO_F1_LEVELS,
  isoF1Curve,
  pointAtThreshold,
  type PrPoint,
  thresholdNearestRecall,
} from "./pr-math";
import { useElementWidth } from "./use-element-width";
import { useReportHint } from "./use-report-hint";

const MARGIN = { top: 24, right: 48, bottom: 36, left: 44 } as const;
const TICKS = [0, 0.25, 0.5, 0.75, 1] as const;
const TICK_TEXT = "fill-text-tertiary font-mono text-[10.5px]";
const LABEL_WIDTH = 104;

type Scale = { x: (recall: number) => number; y: (precision: number) => number };

function linePath(points: readonly PrPoint[], scale: Scale): string {
  return points
    .map(
      (point, index) =>
        `${index ? "L" : "M"}${scale.x(point.recall).toFixed(1)} ${scale.y(point.precision).toFixed(1)}`,
    )
    .join("");
}

function describe(model: ModelEvaluation, chosen: PrCurvePoint | null): string {
  const at = (threshold: number) => {
    const point = pointAtThreshold(model.prCurve, threshold);
    return `при пороге ${formatShare(threshold)} точность ${formatShare(point.precision)}, полнота ${formatShare(point.recall)}`;
  };
  const parts = [
    `PR-кривая модели ${model.name}, класс «мусор».`,
    `Рабочий порог: ${at(model.threshold)}.`,
    chosen && Math.abs(chosen.threshold - model.threshold) > 0.001
      ? `Выбранный порог: ${at(chosen.threshold)}.`
      : null,
    `Для сравнения: ${at(0.3)}; ${at(0.7)}.`,
  ];
  return parts.filter(Boolean).join(" ");
}

function Grid({ width, height, scale }: { width: number; height: number; scale: Scale }) {
  return (
    <g aria-hidden>
      {TICKS.map((tick) => (
        <g key={`y${tick}`}>
          <line
            x1={MARGIN.left}
            x2={width - MARGIN.right}
            y1={Math.round(scale.y(tick)) + 0.5}
            y2={Math.round(scale.y(tick)) + 0.5}
            className={tick === 0 ? "stroke-line-control" : "stroke-line-hairline"}
          />
          <text
            x={MARGIN.left - 7}
            y={scale.y(tick)}
            textAnchor="end"
            dominantBaseline="middle"
            className={TICK_TEXT}
          >
            {formatShare(tick)}
          </text>
        </g>
      ))}
      {TICKS.map((tick) => (
        <g key={`x${tick}`}>
          <line
            x1={Math.round(scale.x(tick)) + 0.5}
            x2={Math.round(scale.x(tick)) + 0.5}
            y1={MARGIN.top}
            y2={height - MARGIN.bottom}
            className={tick === 0 ? "stroke-line-control" : "stroke-line-hairline"}
          />
          <text
            x={scale.x(tick)}
            y={height - MARGIN.bottom + 15}
            textAnchor="middle"
            className={TICK_TEXT}
          >
            {formatShare(tick)}
          </text>
        </g>
      ))}
      <text x={MARGIN.left} y={MARGIN.top - 10} className="fill-text-secondary text-[11px]">
        {PR_COPY.yAxis}
      </text>
      <text
        x={width - MARGIN.right}
        y={height - 3}
        textAnchor="end"
        className="fill-text-secondary text-[11px]"
      >
        {PR_COPY.xAxis}
      </text>
    </g>
  );
}

function IsoLines({ scale }: { scale: Scale }) {
  return (
    <g aria-hidden>
      {ISO_F1_LEVELS.map((level) => {
        const points = isoF1Curve(level);
        const end = points[points.length - 1];
        return (
          <g key={level}>
            <path
              d={linePath(points, scale)}
              fill="none"
              strokeDasharray="1 3"
              strokeLinecap="round"
              className="stroke-text-tertiary"
            />
            <text
              x={scale.x(1) + 6}
              y={scale.y(end.precision)}
              dominantBaseline="middle"
              className="fill-text-tertiary font-mono text-[10.5px]"
            >
              F1 {formatShare(level).replace(/0$/, "")}
            </text>
          </g>
        );
      })}
    </g>
  );
}

function ChosenMark({
  point,
  scale,
  bottom,
}: {
  point: PrCurvePoint;
  scale: Scale;
  bottom: number;
}) {
  const cx = scale.x(point.recall);
  const cy = scale.y(point.precision);
  const labelRight = cx - LABEL_WIDTH - 12 < MARGIN.left;
  return (
    <g aria-hidden>
      <path
        d={`M${cx.toFixed(1)} ${cy.toFixed(1)}V${bottom}M${cx.toFixed(1)} ${cy.toFixed(1)}H${MARGIN.left}`}
        strokeDasharray="2 3"
        className="stroke-accent-selection"
        fill="none"
      />
      <circle
        cx={cx}
        cy={cy}
        r={5}
        strokeWidth={1.5}
        className="fill-accent-selection stroke-surface-panel"
      />
      <text
        x={labelRight ? cx + 10 : cx - 10}
        y={cy - 10}
        textAnchor={labelRight ? "start" : "end"}
        paintOrder="stroke"
        strokeWidth={4}
        strokeLinejoin="round"
        className="fill-text-primary stroke-surface-panel font-mono text-[11px] font-medium"
      >
        P {formatShare(point.precision)} · R {formatShare(point.recall)}
      </text>
    </g>
  );
}

type PrChartProps = {
  model: ModelEvaluation | null;
  threshold: number | null;
  onThreshold: (value: number) => void;
};

export function PrChart({ model, threshold, onThreshold }: PrChartProps) {
  const [containerRef, width] = useElementWidth<HTMLDivElement>();
  const hint = useReportHint();
  const draggingRef = useRef(false);
  const height = Math.round(Math.min(340, Math.max(236, width * 0.64)));
  const plotWidth = Math.max(1, width - MARGIN.left - MARGIN.right);
  const plotHeight = height - MARGIN.top - MARGIN.bottom;
  const bottom = height - MARGIN.bottom;
  const scale: Scale = {
    x: (recall) => MARGIN.left + recall * plotWidth,
    y: (precision) => MARGIN.top + (1 - precision) * plotHeight,
  };
  const curve = model?.prCurve ?? null;
  const chosen = curve && threshold !== null ? pointAtThreshold(curve, threshold) : null;
  const operating = curve && model ? pointAtThreshold(curve, model.threshold) : null;
  const byRecall = curve ? [...curve].sort((a, b) => a.recall - b.recall) : [];

  const pick = (event: PointerEvent<SVGRectElement>) => {
    if (!curve) return;
    const box = event.currentTarget.getBoundingClientRect();
    const recall = Math.min(1, Math.max(0, (event.clientX - box.left) / box.width));
    onThreshold(thresholdNearestRecall(curve, recall));
  };

  return (
    <div ref={containerRef} className="w-full">
      {width > 0 ? (
        <svg
          width={width}
          height={height}
          viewBox={`0 0 ${width} ${height}`}
          role="img"
          aria-label={model ? describe(model, chosen) : `PR-кривая: ${PR_COPY.empty.toLowerCase()}`}
          className="block select-none"
        >
          <Grid width={width} height={height} scale={scale} />
          <IsoLines scale={scale} />
          {curve ? (
            <path
              d={linePath(byRecall, scale)}
              fill="none"
              strokeWidth={2}
              strokeLinejoin="round"
              strokeLinecap="round"
              className="stroke-text-primary"
            />
          ) : (
            <text
              x={MARGIN.left + plotWidth / 2}
              y={MARGIN.top + plotHeight / 2}
              textAnchor="middle"
              dominantBaseline="middle"
              paintOrder="stroke"
              strokeWidth={6}
              strokeLinejoin="round"
              className="fill-text-tertiary stroke-surface-panel text-[12px]"
            >
              {PR_COPY.empty}
            </text>
          )}
          {operating ? (
            <circle
              cx={scale.x(operating.recall)}
              cy={scale.y(operating.precision)}
              r={4}
              strokeWidth={1.5}
              className="fill-surface-panel stroke-text-primary"
            />
          ) : null}
          {chosen ? <ChosenMark point={chosen} scale={scale} bottom={bottom} /> : null}
          {curve ? (
            <rect
              x={MARGIN.left}
              y={MARGIN.top}
              width={plotWidth}
              height={plotHeight}
              fill="transparent"
              className="cursor-crosshair"
              style={{ touchAction: "pan-y" }}
              onPointerDown={(event) => {
                draggingRef.current = true;
                event.currentTarget.setPointerCapture(event.pointerId);
                pick(event);
              }}
              onPointerMove={(event) => {
                if (draggingRef.current) pick(event);
              }}
              onPointerUp={() => {
                draggingRef.current = false;
              }}
              onPointerCancel={() => {
                draggingRef.current = false;
              }}
              onPointerEnter={() => hint.show(PR_COPY.hint)}
              onPointerLeave={hint.restore}
            />
          ) : null}
        </svg>
      ) : (
        <div style={{ height: 280 }} />
      )}
    </div>
  );
}
