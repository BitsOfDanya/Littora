import { formatNumber } from "@/lib/format/numbers";
import { formatShortDate } from "@/lib/format/time";

export type SeriesPoint = {
  id: string;
  time: string;
  state: "observed" | "not-found" | "cloudy" | "no-data";
  value?: number;
  low?: number;
  high?: number;
  cloudCover?: number;
};

type ObservationSeriesProps = {
  points: readonly SeriesPoint[];
  selectedId?: string | null;
  markers?: readonly { id: string; label: string }[];
  unit: string;
  title: string;
  onSelect?: (id: string) => void;
  describe?: (point: SeriesPoint) => string;
};

const WIDTH = 344;
const HEIGHT = 132;
const PAD = { top: 10, right: 10, bottom: 22, left: 30 };

function defaultDescription(point: SeriesPoint): string {
  const day = formatShortDate(point.time);
  if (point.state === "observed" && point.value !== undefined) {
    const interval =
      point.low !== undefined && point.high !== undefined
        ? ` (90 % ДИ ${formatNumber(point.low * 100, 0)}–${formatNumber(point.high * 100, 0)})`
        : "";
    return `${day}: найдено · ${formatNumber(point.value * 100, 0)} %${interval}`;
  }
  if (point.state === "not-found") return `${day}: не найдено`;
  if (point.state === "cloudy")
    return `${day}: облачно${point.cloudCover !== undefined ? ` ${formatNumber(point.cloudCover * 100, 0)} %` : ""} — нет данных`;
  return `${day}: нет данных`;
}

function splitSegments(points: readonly SeriesPoint[]): SeriesPoint[][] {
  const segments: SeriesPoint[][] = [];
  let current: SeriesPoint[] = [];
  for (const point of points) {
    if (point.state === "observed" && point.value !== undefined) current.push(point);
    else if (point.state === "cloudy" || point.state === "no-data") {
      if (current.length) segments.push(current);
      current = [];
    }
  }
  if (current.length) segments.push(current);
  return segments;
}

export function ObservationSeries({
  points,
  selectedId,
  markers = [],
  unit,
  title,
  onSelect,
  describe = defaultDescription,
}: ObservationSeriesProps) {
  if (!points.length) return null;
  const times = points.map((point) => Date.parse(point.time));
  const minTime = Math.min(...times);
  const span = Math.max(1, Math.max(...times) - minTime);
  const maxValue = Math.max(0.01, ...points.map((point) => point.high ?? point.value ?? 0)) * 1.15;
  const x = (time: string) =>
    PAD.left + ((Date.parse(time) - minTime) / span) * (WIDTH - PAD.left - PAD.right);
  const y = (value: number) => PAD.top + (1 - value / maxValue) * (HEIGHT - PAD.top - PAD.bottom);
  const segments = splitSegments(points);
  const selected = points.find((point) => point.id === selectedId);
  const labelEvery = Math.ceil(points.length / 6);

  return (
    <figure className="flex flex-col gap-1">
      <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} role="img" aria-label={title} className="w-full">
        {[0, maxValue / 2, maxValue].map((value) => (
          <g key={value}>
            <line
              x1={PAD.left}
              x2={WIDTH - PAD.right}
              y1={y(value)}
              y2={y(value)}
              stroke="var(--line-hairline)"
            />
            <text
              x={PAD.left - 4}
              y={y(value) + 3}
              textAnchor="end"
              className="fill-text-tertiary font-mono text-[10.5px]"
            >
              {formatNumber(value * 100, 0)}
            </text>
          </g>
        ))}
        {selected ? (
          <line
            x1={x(selected.time)}
            x2={x(selected.time)}
            y1={PAD.top - 4}
            y2={HEIGHT - PAD.bottom}
            stroke="var(--accent-selection)"
            strokeWidth={1.4}
          />
        ) : null}
        {markers.map((marker) => {
          const point = points.find((entry) => entry.id === marker.id);
          if (!point) return null;
          return (
            <g key={marker.label}>
              <line
                x1={x(point.time)}
                x2={x(point.time)}
                y1={PAD.top}
                y2={HEIGHT - PAD.bottom}
                stroke="var(--text-primary)"
                strokeDasharray="2 2"
              />
              <text
                x={x(point.time) + 3}
                y={PAD.top + 9}
                className="fill-text-primary font-mono text-[10.5px]"
              >
                {marker.label}
              </text>
            </g>
          );
        })}
        {segments.map((segment) => (
          <polyline
            key={segment[0].id}
            fill="none"
            stroke="var(--text-primary)"
            strokeWidth={1.4}
            points={segment.map((point) => `${x(point.time)},${y(point.value ?? 0)}`).join(" ")}
          />
        ))}
        {points.map((point) => {
          const cx = x(point.time);
          const isSelected = point.id === selectedId;
          const accent = isSelected ? "var(--accent-selection)" : undefined;
          let mark;
          if (point.state === "observed" && point.value !== undefined) {
            mark = (
              <>
                {point.low !== undefined && point.high !== undefined ? (
                  <g stroke={accent ?? "var(--text-secondary)"}>
                    <line x1={cx} x2={cx} y1={y(point.low)} y2={y(point.high)} />
                    <line x1={cx - 2.5} x2={cx + 2.5} y1={y(point.low)} y2={y(point.low)} />
                    <line x1={cx - 2.5} x2={cx + 2.5} y1={y(point.high)} y2={y(point.high)} />
                  </g>
                ) : null}
                <circle
                  cx={cx}
                  cy={y(point.value)}
                  r={isSelected ? 3.6 : 2.6}
                  fill={accent ?? "var(--text-primary)"}
                />
              </>
            );
          } else if (point.state === "not-found") {
            mark = (
              <circle
                cx={cx}
                cy={y(0)}
                r={2.6}
                fill="var(--surface-panel)"
                stroke={accent ?? "var(--text-secondary)"}
              />
            );
          } else {
            mark = (
              <rect
                x={cx - 3}
                y={HEIGHT - PAD.bottom - 7}
                width={6}
                height={6}
                fill="none"
                stroke={accent ?? "var(--text-tertiary)"}
                strokeDasharray="1.5 1.5"
              />
            );
          }
          const description = describe(point);
          return (
            <g
              key={point.id}
              role={onSelect ? "button" : undefined}
              tabIndex={onSelect ? 0 : undefined}
              aria-label={onSelect ? description : undefined}
              aria-pressed={onSelect ? isSelected : undefined}
              onClick={onSelect ? () => onSelect(point.id) : undefined}
              onKeyDown={
                onSelect
                  ? (event) => {
                      if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        onSelect(point.id);
                      }
                    }
                  : undefined
              }
              className={
                onSelect
                  ? "cursor-pointer outline-none focus-visible:[&>rect:first-child]:stroke-focus-ring"
                  : undefined
              }
            >
              <title>{description}</title>
              <rect
                x={cx - 7}
                y={PAD.top - 4}
                width={14}
                height={HEIGHT - PAD.top - PAD.bottom + 8}
                fill="transparent"
                stroke="transparent"
                strokeWidth={2}
              />
              {mark}
            </g>
          );
        })}
        {points.map((point, index) =>
          index % labelEvery === 0 ? (
            <text
              key={`t-${point.id}`}
              x={x(point.time)}
              y={HEIGHT - 6}
              textAnchor="middle"
              className="fill-text-tertiary font-mono text-[10.5px]"
            >
              {formatShortDate(point.time)}
            </text>
          ) : null,
        )}
      </svg>
      <figcaption className="text-[11px] leading-[14px] text-text-tertiary">
        {unit} · ● найдено с 90 % ДИ · ○ не найдено · ⬚ облачно или нет данных — линия разорвана,
        без интерполяции
      </figcaption>
    </figure>
  );
}
