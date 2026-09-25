import { type ReactNode, useId } from "react";
import { GROUND_INK } from "@/features/map/palette";
import {
  BEACHING,
  type ByGround,
  CONFIDENCE_INK,
  CONFIDENCE_LINES,
  type ConfidenceLevel,
  DRIFT,
  type Ground,
  NO_DATA,
  SURVEY,
  UNCERTAINTY,
} from "@/features/map/ramps";

const GROUND_TILE: ByGround<string> = { dark: "#0F1B24", light: "#D4E6EC" };

const WIDTH = 26;
const HEIGHT = 14;
const MID = HEIGHT / 2;

function GroundSwatch({
  ground,
  width = WIDTH,
  children,
}: {
  ground: Ground;
  width?: number;
  children: ReactNode;
}) {
  return (
    <svg
      width={width}
      height={HEIGHT}
      viewBox={`0 0 ${width} ${HEIGHT}`}
      aria-hidden
      className="shrink-0"
    >
      <rect
        x="0.5"
        y="0.5"
        width={width - 1}
        height={HEIGHT - 1}
        fill={GROUND_TILE[ground]}
        className="stroke-line-hairline"
      />
      {children}
    </svg>
  );
}

function HatchPattern({
  id,
  color,
  spacing,
  angle,
  width = 1,
}: {
  id: string;
  color: string;
  spacing: number;
  angle: number;
  width?: number;
}) {
  return (
    <pattern
      id={id}
      width={spacing}
      height={spacing}
      patternUnits="userSpaceOnUse"
      patternTransform={`rotate(${angle})`}
    >
      <line x1="0" y1="0" x2="0" y2={spacing} stroke={color} strokeWidth={width} />
    </pattern>
  );
}

const dashOf = (dash: readonly number[]) => (dash[0] === 0 ? undefined : dash.join(" "));

export function ConfidenceSwatch({ level, ground }: { level: ConfidenceLevel; ground: Ground }) {
  const id = useId();
  const style = CONFIDENCE_LINES[level];
  const ink = CONFIDENCE_INK[ground];
  return (
    <GroundSwatch ground={ground}>
      {level === "low" ? (
        <defs>
          <HatchPattern id={id} color={ink.lowHatch} spacing={3} angle={45} />
        </defs>
      ) : null}
      <rect
        x="4"
        y="4"
        width={WIDTH - 8}
        height={HEIGHT - 8}
        fill={level === "low" ? `url(#${id})` : "none"}
        stroke={ink.outline}
        strokeWidth={style.widthPx}
        strokeDasharray={dashOf(style.dash)}
      />
    </GroundSwatch>
  );
}

export function UncertaintySwatch({ dense, ground }: { dense: boolean; ground: Ground }) {
  const id = useId();
  return (
    <GroundSwatch ground={ground}>
      <defs>
        <HatchPattern
          id={id}
          color={UNCERTAINTY.ink[ground].hatch}
          spacing={dense ? 2.5 : 4.5}
          angle={45}
        />
      </defs>
      <rect x="1" y="1" width={WIDTH - 2} height={HEIGHT - 2} fill={`url(#${id})`} />
    </GroundSwatch>
  );
}

export function NoDataSwatch({ ground }: { ground: Ground }) {
  const forward = useId();
  const backward = useId();
  const ink = NO_DATA.ink[ground];
  return (
    <GroundSwatch ground={ground}>
      <defs>
        <HatchPattern id={forward} color={ink.line} spacing={4} angle={45} />
        <HatchPattern id={backward} color={ink.line} spacing={4} angle={-45} />
      </defs>
      <rect x="1" y="1" width={WIDTH - 2} height={HEIGHT - 2} fill={ink.underlay} />
      <g opacity={NO_DATA.lineAlpha}>
        <rect x="1" y="1" width={WIDTH - 2} height={HEIGHT - 2} fill={`url(#${forward})`} />
        <rect x="1" y="1" width={WIDTH - 2} height={HEIGHT - 2} fill={`url(#${backward})`} />
      </g>
      <rect
        x="2.5"
        y="2.5"
        width={WIDTH - 5}
        height={HEIGHT - 5}
        fill="none"
        stroke={ink.line}
        strokeWidth={1}
        strokeDasharray="2.5 2"
      />
    </GroundSwatch>
  );
}

type LineSwatchProps = {
  ground: Ground;
  color: string;
  width: number;
  dash?: string;
  halo?: { color: string; width: number };
  round?: boolean;
  opacity?: number;
};

export function LineSwatch({ ground, color, width, dash, halo, round, opacity }: LineSwatchProps) {
  const cap = round ? "round" : "butt";
  return (
    <GroundSwatch ground={ground}>
      {halo ? (
        <line
          x1="5"
          x2={WIDTH - 5}
          y1={MID}
          y2={MID}
          stroke={halo.color}
          strokeWidth={halo.width}
          strokeLinecap={cap}
        />
      ) : null}
      <line
        x1="5"
        x2={WIDTH - 5}
        y1={MID}
        y2={MID}
        stroke={color}
        strokeWidth={width}
        strokeDasharray={dash}
        strokeLinecap={cap}
        opacity={opacity}
      />
    </GroundSwatch>
  );
}

export function FootprintSwatch({ ground }: { ground: Ground }) {
  return (
    <GroundSwatch ground={ground}>
      <rect
        x="4"
        y="3.5"
        width={WIDTH - 8}
        height={HEIGHT - 7}
        fill="none"
        stroke={GROUND_INK[ground].outline}
        strokeWidth={1}
        strokeDasharray="1 2"
      />
    </GroundSwatch>
  );
}

export function AoiSwatch({ ground }: { ground: Ground }) {
  return <LineSwatch ground={ground} color={GROUND_INK[ground].aoi} width={1.5} dash="6 3" />;
}

export function EnvelopeSwatch({ ground, alpha }: { ground: Ground; alpha: number }) {
  const color = DRIFT.ink[ground].envelope;
  return (
    <GroundSwatch ground={ground}>
      <rect
        x="4"
        y="3"
        width={WIDTH - 8}
        height={HEIGHT - 6}
        fill={color}
        fillOpacity={alpha * 2.4}
        stroke={color}
        strokeWidth={1}
        strokeDasharray="2.5 1.5"
      />
    </GroundSwatch>
  );
}

const NESTED_WIDTH = 52;
const NESTED_RX = [4, 7.5, 11.5, 16, 21] as const;
const NESTED_RY = [2, 2.8, 3.6, 4.4, 5.2] as const;

export function NestedEnvelopesSwatch({
  ground,
  alphas,
}: {
  ground: Ground;
  alphas: readonly number[];
}) {
  const color = DRIFT.ink[ground].envelope;
  const layers = alphas
    .map((alpha, index) => ({ alpha, rx: NESTED_RX[index] ?? 21, ry: NESTED_RY[index] ?? 5.2 }))
    .reverse();
  return (
    <GroundSwatch ground={ground} width={NESTED_WIDTH}>
      {layers.map(({ alpha, rx, ry }) => (
        <ellipse
          key={rx}
          cx={4 + rx}
          cy={MID}
          rx={rx}
          ry={ry}
          fill={color}
          fillOpacity={alpha * 1.8}
          stroke={color}
          strokeOpacity={0.9}
          strokeWidth={0.8}
          strokeDasharray="2 1.4"
        />
      ))}
    </GroundSwatch>
  );
}

export function MedianSwatch({ ground }: { ground: Ground }) {
  const color = DRIFT.ink[ground].median;
  return (
    <GroundSwatch ground={ground}>
      <line
        x1="3"
        x2={WIDTH - 3}
        y1={MID}
        y2={MID}
        stroke={color}
        strokeWidth={1.4}
        strokeDasharray={DRIFT.medianDash.map((value) => value * 0.6).join(" ")}
      />
      <circle
        cx={WIDTH / 2}
        cy={MID}
        r="2.6"
        fill={GROUND_TILE[ground]}
        stroke={color}
        strokeWidth={1.2}
      />
    </GroundSwatch>
  );
}

export function HindcastSwatch({ ground }: { ground: Ground }) {
  return (
    <LineSwatch
      ground={ground}
      color={DRIFT.ink[ground].median}
      width={1.4}
      dash={DRIFT.hindcastDash.join(" ")}
      round
    />
  );
}

export function ParticlesSwatch({ ground }: { ground: Ground }) {
  const ink = DRIFT.ink[ground];
  return (
    <GroundSwatch ground={ground}>
      {[
        [4, 4.5, 11],
        [9, 9.5, 17],
        [15, 5.5, 22],
      ].map(([start, y, end]) => (
        <line
          key={start}
          x1={start}
          x2={end}
          y1={y}
          y2={y - 1}
          stroke={ink.particle}
          strokeOpacity={ink.particleAlpha * 2.2}
          strokeWidth={1.4}
          strokeLinecap="round"
        />
      ))}
    </GroundSwatch>
  );
}

export function BeachingSwatch({
  ground,
  severity,
}: {
  ground: Ground;
  severity: "alarm" | "caution";
}) {
  const ink = BEACHING.ink[ground];
  return (
    <LineSwatch
      ground={ground}
      color={ink[severity]}
      width={4}
      round
      halo={{ color: ink.halo, width: 6 }}
    />
  );
}

export function TargetSwatch({ ground }: { ground: Ground }) {
  const ink = SURVEY.ink[ground];
  return (
    <GroundSwatch ground={ground}>
      <circle
        cx={WIDTH / 2}
        cy={MID}
        r="5.2"
        fill={ink.ringFill}
        stroke={ink.mark}
        strokeWidth={1.6}
      />
      <text
        x={WIDTH / 2}
        y={MID + 2.6}
        textAnchor="middle"
        fontSize="7.5"
        fontWeight="700"
        fill={ink.mark}
        className="font-mono"
      >
        1
      </text>
    </GroundSwatch>
  );
}

export function RouteSwatch({ ground }: { ground: Ground }) {
  return (
    <LineSwatch
      ground={ground}
      color={SURVEY.ink[ground].mark}
      width={SURVEY.routeWidthPx}
      dash={SURVEY.routeDash.map((value) => value / 2).join(" ")}
      halo={{ color: GROUND_INK[ground].halo, width: 4 }}
    />
  );
}

export function SearchRadiusSwatch({ ground }: { ground: Ground }) {
  return (
    <GroundSwatch ground={ground}>
      <circle
        cx={WIDTH / 2}
        cy={MID}
        r="5"
        fill="none"
        stroke={SURVEY.ink[ground].mark}
        strokeWidth={SURVEY.searchRadiusWidthPx}
        strokeDasharray={SURVEY.searchRadiusDash.join(" ")}
      />
    </GroundSwatch>
  );
}
