"use client";

import { type KeyboardEvent, useEffect, useState } from "react";
import type { BeachSegmentRisk, DriftForecastDetail, ForecastRun } from "@/data/forecast";
import { useForecastRun } from "@/data/forecast";
import { FORECAST_HORIZONS_H, type ForecastHorizonH } from "@/domain/forecast";
import { DemoAction } from "@/features/cartouche/planned-group-note";
import { formatUtcDateTime } from "@/lib/format/time";
import { useMapLayersStore, useParticlesPaused } from "@/state/map-layers-store";
import { useWorkspaceStore } from "@/state/workspace-store";
import { Button, IconButton } from "@/ui/button";
import { cn } from "@/ui/cn";
import { DemoTag } from "@/ui/demo-mark";
import { IconChevronLeft, IconChevronRight, IconPause, IconPlay } from "@/ui/icons";
import { SeverityGlyph } from "@/ui/indicators";
import { Kbd } from "@/ui/kbd";
import { Caps } from "@/ui/section";
import {
  elapsedLabel,
  horizonLabel,
  RELIABILITY_LIMIT_H,
  RELIABILITY_WORD,
  shiftIso,
} from "./drift-math";
import { formatProbability } from "./forecast-copy";
import { chooseHorizon, stepHorizonBy } from "./forecast-hotkeys";
import { RAIL_T0_ID } from "./forecast-model";
import { useForecastUiStore } from "./forecast-ui-store";
import { togglePlayback } from "./use-horizon-playback";
import { useSelectedForecast } from "./use-selected-forecast";

const AXIS_FROM_H = -48;
const AXIS_TO_H = 72;
const AXIS_SPAN_H = AXIS_TO_H - AXIS_FROM_H;
const AXIS_LABELS_H = [-48, -24, 24, 48, 72] as const;
const CHIP_WIDTH_PX = 34;
const NOW_REFRESH_MS = 60_000;
const LAST_HORIZON = FORECAST_HORIZONS_H[FORECAST_HORIZONS_H.length - 1];

function formatRunTime(iso: string): string {
  const stamp = formatUtcDateTime(iso);
  return stamp.endsWith(":00Z") ? `${stamp.slice(0, -4)}Z` : stamp;
}

function shortStamp(iso: string): string {
  return `${iso.slice(8, 10)}.${iso.slice(5, 7)} ${iso.slice(11, 16)}Z`;
}

function ratioOf(hours: number): number {
  return (Math.min(Math.max(hours, AXIS_FROM_H), AXIS_TO_H) - AXIS_FROM_H) / AXIS_SPAN_H;
}

function at(hours: number): string {
  return `${ratioOf(hours) * 100}%`;
}

function span(fromH: number, toH: number) {
  return { left: at(fromH), width: `${(ratioOf(toH) - ratioOf(fromH)) * 100}%` };
}

function useNow(): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), NOW_REFRESH_MS);
    return () => window.clearInterval(timer);
  }, []);
  return now;
}

function useTrackWidth(): [(element: HTMLDivElement | null) => void, number] {
  const [element, setElement] = useState<HTMLDivElement | null>(null);
  const [width, setWidth] = useState(0);
  useEffect(() => {
    if (!element) return;
    const observer = new ResizeObserver(([entry]) => setWidth(entry.contentRect.width));
    observer.observe(element);
    return () => observer.disconnect();
  }, [element]);
  return [setElement, width];
}

function chipOffsets(width: number): Record<ForecastHorizonH, number> {
  const positions = FORECAST_HORIZONS_H.map((hour) => ratioOf(hour) * width);
  const shifted = [...positions];
  for (let index = 1; index < shifted.length; index += 1) {
    const gap = shifted[index] - shifted[index - 1];
    if (gap < CHIP_WIDTH_PX + 2) {
      const push = (CHIP_WIDTH_PX + 2 - gap) / 2;
      shifted[index - 1] -= push;
      shifted[index] += push;
    }
  }
  return Object.fromEntries(
    FORECAST_HORIZONS_H.map((hour, index) => [hour, shifted[index] - positions[index]]),
  ) as Record<ForecastHorizonH, number>;
}

type ControlProps = {
  horizonH: ForecastHorizonH;
  run: ForecastRun | null;
  isDemo: boolean;
  now: number;
};

function ParticlesButton({ disabled }: { disabled?: boolean }) {
  const paused = useParticlesPaused();
  const toggle = useMapLayersStore((state) => state.toggleParticlesPaused);
  return (
    <Button
      size="sm"
      disabled={disabled}
      aria-pressed={paused}
      aria-keyshortcuts="M"
      title={paused ? "Запустить частицы течений · M" : "Остановить частицы течений · M"}
      icon={paused ? <IconPlay size={12} /> : <IconPause size={12} />}
      onClick={toggle}
    >
      Частицы
      <Kbd className="h-4 min-w-4">M</Kbd>
    </Button>
  );
}

function PlayButton({ disabled }: { disabled?: boolean }) {
  const playing = useForecastUiStore((state) => state.playing);
  return (
    <Button
      size="sm"
      disabled={disabled}
      aria-pressed={playing}
      aria-keyshortcuts="Space"
      title={playing ? "Пауза · Space" : "Пуск по горизонтам 0 → +72 ч · Space"}
      icon={playing ? <IconPause size={12} /> : <IconPlay size={12} />}
      onClick={togglePlayback}
    >
      {playing ? "Пауза" : `0 → +72`}
    </Button>
  );
}

function ControlBlock({ horizonH, run, isDemo, now }: ControlProps) {
  const index = FORECAST_HORIZONS_H.indexOf(horizonH);
  return (
    <div className="flex min-w-0 flex-col justify-center gap-1 border-r border-line-hairline px-3 py-1.5">
      <div className="flex min-w-0 items-center gap-1.5">
        <Caps className="text-text-secondary">Горизонт прогноза</Caps>
        <span className="hidden text-[11px] leading-[14px] text-text-tertiary min-[1600px]:inline">
          от снимка T₀
        </span>
        {isDemo ? <DemoTag className="ml-auto" /> : null}
      </div>
      {run ? (
        <>
          <div className="flex items-center gap-1">
            <span className="mr-0.5 min-w-[52px] font-mono text-[17px] leading-[22px] font-semibold text-text-primary">
              {horizonLabel(horizonH)}
            </span>
            <IconButton
              label="Меньший горизонт"
              shortcut="["
              size="sm"
              disabled={index <= 0}
              onClick={() => stepHorizonBy(-1)}
            >
              <IconChevronLeft />
            </IconButton>
            <IconButton
              label="Больший горизонт"
              shortcut="]"
              size="sm"
              disabled={horizonH === LAST_HORIZON}
              onClick={() => stepHorizonBy(1)}
            >
              <IconChevronRight />
            </IconButton>
            <PlayButton />
          </div>
          <p
            className="truncate text-[11px] leading-[14px] text-text-secondary"
            title={`цель ${formatUtcDateTime(shiftIso(run.t0, horizonH))} · от снимка T₀ ${formatUtcDateTime(run.t0)} · сейчас ${elapsedLabel(run.t0, now)}`}
          >
            цель <span className="font-mono">{shortStamp(shiftIso(run.t0, horizonH))}</span> ·
            сейчас <span className="font-mono">{elapsedLabel(run.t0, now)}</span>
          </p>
          <div className="flex items-center gap-1.5">
            <ParticlesButton />
          </div>
        </>
      ) : (
        <>
          <p className="text-[13px] leading-4 text-text-primary">Прогноз не подключён</p>
          <p className="font-mono text-[11px] leading-[14px] text-text-tertiary">
            drift_forecast: planned
          </p>
          <div className="[&_button]:h-6 [&_button]:px-2 [&_button]:text-[12px]">
            <DemoAction />
          </div>
        </>
      )}
    </div>
  );
}

function HorizonChips({
  horizonH,
  width,
  disabled,
}: {
  horizonH: ForecastHorizonH;
  width: number;
  disabled: boolean;
}) {
  const offsets = chipOffsets(width);
  const handleKey = (event: KeyboardEvent<HTMLButtonElement>) => {
    const delta = event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : 0;
    if (!delta) return;
    event.preventDefault();
    stepHorizonBy(delta);
    const next =
      FORECAST_HORIZONS_H[
        Math.min(
          Math.max(FORECAST_HORIZONS_H.indexOf(horizonH) + delta, 0),
          FORECAST_HORIZONS_H.length - 1,
        )
      ];
    const group = event.currentTarget.parentElement;
    requestAnimationFrame(() =>
      group?.querySelector<HTMLButtonElement>(`[data-horizon="${next}"]`)?.focus(),
    );
  };
  return (
    <div role="radiogroup" aria-label="Горизонт прогноза на шкале" className="relative h-full">
      {FORECAST_HORIZONS_H.map((hour) => {
        const active = hour === horizonH;
        return (
          <button
            key={hour}
            type="button"
            role="radio"
            aria-checked={active}
            data-horizon={hour}
            tabIndex={active ? 0 : -1}
            disabled={disabled}
            onClick={() => chooseHorizon(hour)}
            onKeyDown={handleKey}
            title={`+${hour} ч · цель от снимка T₀ · надёжность ${RELIABILITY_WORD[hour <= 24 ? "high" : hour <= 48 ? "medium" : "low"]}`}
            style={{ left: `calc(${at(hour)} + ${offsets[hour]}px)`, width: CHIP_WIDTH_PX }}
            className={cn(
              "absolute top-1/2 h-5 -translate-x-1/2 -translate-y-1/2 rounded-[var(--radius-ctl)] border font-mono text-[11px] leading-none transition-colors duration-[var(--t-2)]",
              active
                ? "border-accent-selection bg-accent-selection font-semibold text-text-inverse"
                : "border-line-control bg-surface-panel text-text-secondary hover:border-line-strong hover:text-text-primary",
              disabled &&
                "cursor-not-allowed border-dashed bg-transparent text-text-disabled hover:border-line-control hover:text-text-disabled",
            )}
          >
            +{hour}
          </button>
        );
      })}
    </div>
  );
}

function ReliabilityBand() {
  const bands = [
    { from: 0, to: RELIABILITY_LIMIT_H.high, word: RELIABILITY_WORD.high, alpha: 0.46 },
    {
      from: RELIABILITY_LIMIT_H.high,
      to: RELIABILITY_LIMIT_H.medium,
      word: RELIABILITY_WORD.medium,
      alpha: 0.28,
    },
    { from: RELIABILITY_LIMIT_H.medium, to: AXIS_TO_H, word: RELIABILITY_WORD.low, alpha: 0.13 },
  ];
  return (
    <div
      className="relative h-full"
      role="img"
      aria-label="Надёжность: высокая до +24 ч, средняя до +48 ч, дальше низкая — ориентир"
    >
      <span
        className="absolute inset-y-0 flex items-center overflow-hidden pl-1 text-[11px] whitespace-nowrap text-text-tertiary"
        style={span(AXIS_FROM_H, 0)}
      >
        обратный дрейф — откуда пришло
      </span>
      {bands.map((band) => (
        <span
          key={band.word}
          title={`Надёжность ${band.word}`}
          className="absolute inset-y-px flex items-center overflow-hidden border-l border-surface-panel px-1 text-[11px] leading-none whitespace-nowrap text-text-primary"
          style={{
            ...span(band.from, band.to),
            backgroundColor: `color-mix(in srgb, var(--text-secondary) ${Math.round(band.alpha * 100)}%, transparent)`,
          }}
        >
          {band.word}
        </span>
      ))}
    </div>
  );
}

function RiskMarks({ forecast }: { forecast: DriftForecastDetail }) {
  const risks = forecast.beaching.filter(
    (risk): risk is BeachSegmentRisk & { severity: "alarm" | "caution" } =>
      risk.severity !== "info",
  );
  const source = forecast.sources[0]?.position ? forecast.sources[0] : null;
  return (
    <div className="relative h-full">
      {source ? (
        <span
          className="absolute inset-y-0 flex items-center gap-1 pl-1 text-[11px] whitespace-nowrap text-text-secondary"
          style={{ left: at(AXIS_FROM_H) }}
          title={`Вероятный источник: ${source.name} · ${formatProbability(source.probability.value)}`}
        >
          <span aria-hidden className="size-2 rounded-full border border-text-secondary" />
          {source.name.replace("Устье ", "устье ")} · {formatProbability(source.probability.value)}
        </span>
      ) : null}
      {risks.map((risk, index) => (
        <span
          key={risk.id}
          className="absolute flex h-full items-center"
          style={span(risk.windowH[0], Math.max(risk.windowH[1], risk.windowH[0] + 1))}
          title={`${risk.name} · вынос через ${risk.windowH[0]}–${risk.windowH[1]} ч · ${formatProbability(risk.probability.value)}`}
        >
          <span
            className={cn(
              "absolute inset-x-0 top-1/2 h-1.5 -translate-y-1/2",
              risk.severity === "alarm" ? "bg-state-alarm" : "bg-state-caution",
              index > 0 && "translate-y-[1px] opacity-80",
            )}
          />
        </span>
      ))}
      {risks[0] ? (
        <span
          className={cn(
            "absolute inset-y-0 flex -translate-x-full items-center gap-1 pr-1.5 text-[11px] whitespace-nowrap",
            risks[0].severity === "alarm" ? "text-state-alarm" : "text-state-caution",
          )}
          style={{ left: at(risks[0].windowH[0]) }}
        >
          <SeverityGlyph severity={risks[0].severity} size={12} />
          {risks[0].name} · {formatProbability(risks[0].probability.value)}
        </span>
      ) : null}
    </div>
  );
}

type TracksProps = {
  horizonH: ForecastHorizonH;
  forecast: DriftForecastDetail | null;
  run: ForecastRun | null;
  isDemo: boolean;
  now: number;
  idleNote: string | null;
};

const LABEL_CLASS = "self-center pr-2 text-[11px] leading-[14px] text-text-tertiary";

function Tracks({ horizonH, forecast, run, isDemo, now, idleNote }: TracksProps) {
  const [trackRef, width] = useTrackWidth();
  const nowHours = run ? (now - Date.parse(run.t0)) / 3_600_000 : null;
  const nowInside = nowHours !== null && nowHours >= AXIS_FROM_H && nowHours <= AXIS_TO_H;
  return (
    <div className="grid h-full min-w-0 grid-cols-[88px_minmax(0,1fr)_132px] py-1.5 pr-3 pl-3 xl:grid-cols-[96px_minmax(0,1fr)_148px]">
      <div className="grid grid-rows-[16px_22px_14px_16px] gap-y-1">
        <span className={LABEL_CLASS}>Часы от T₀</span>
        <span className={LABEL_CLASS}>Горизонт</span>
        <span className={LABEL_CLASS}>Надёжность</span>
        <span className={LABEL_CLASS}>{forecast ? "Берег · источник" : "Прогноз"}</span>
      </div>
      <div ref={trackRef} className="relative grid min-w-0 grid-rows-[16px_22px_14px_16px] gap-y-1">
        <span
          aria-hidden
          className="absolute -inset-y-1.5 bg-surface-sunken"
          style={span(AXIS_FROM_H, 0)}
        />
        <span
          aria-hidden
          className="absolute -inset-y-1.5 bg-[repeating-linear-gradient(45deg,var(--line-hairline)_0_1px,transparent_1px_6px)]"
          style={span(0, AXIS_TO_H)}
        />
        <div className="relative border-b border-line-control">
          {AXIS_LABELS_H.map((hour) => (
            <span
              key={hour}
              className="absolute bottom-0 h-1.5 border-l border-line-control"
              style={{ left: at(hour) }}
            >
              <span
                className={cn(
                  "absolute bottom-1 font-mono text-[10.5px] leading-3 font-medium whitespace-nowrap text-text-tertiary",
                  hour === AXIS_TO_H ? "right-1" : "left-1",
                )}
              >
                {horizonLabel(hour)}
              </span>
            </span>
          ))}
          {FORECAST_HORIZONS_H.map((hour) => (
            <span
              key={`tick-${hour}`}
              aria-hidden
              className="absolute bottom-0 h-1 border-l border-line-control"
              style={{ left: at(hour) }}
            />
          ))}
          <span
            id={RAIL_T0_ID}
            tabIndex={-1}
            className="absolute bottom-1 left-0 -translate-x-full pr-1 font-mono text-[10.5px] leading-3 font-semibold whitespace-nowrap text-text-primary focus-visible:outline-2"
            style={{ left: at(0) }}
            title={run ? `T₀ — снимок ${formatUtcDateTime(run.t0)}` : "T₀ — снимок"}
          >
            T₀ снимок
          </span>
        </div>
        <HorizonChips horizonH={horizonH} width={width} disabled={!run} />
        <ReliabilityBand />
        {forecast ? (
          <RiskMarks forecast={forecast} />
        ) : (
          <span
            className="relative flex items-center pl-1 text-[11px] whitespace-nowrap text-text-tertiary"
            style={{ marginLeft: at(0) }}
          >
            {idleNote}
          </span>
        )}
        <span
          aria-hidden
          className="pointer-events-none absolute -inset-y-1.5 w-px bg-text-primary"
          style={{ left: at(0) }}
        />
        {run ? (
          <span
            aria-hidden
            className="pointer-events-none absolute -inset-y-1.5 w-0.5 -translate-x-1/2 bg-accent-selection"
            style={{ left: at(horizonH) }}
          />
        ) : null}
        {nowInside ? (
          <span
            aria-hidden
            className="pointer-events-none absolute -inset-y-1.5 border-l border-dashed border-text-secondary"
            style={{ left: at(nowHours) }}
          />
        ) : null}
      </div>
      <div className="flex min-w-0 flex-col justify-between pl-3 text-right">
        {run ? (
          <>
            <span className="font-serif text-[13px] leading-4 text-text-secondary italic">
              прогон {formatRunTime(run.runAt)}
              {isDemo ? " · демо" : ""}
            </span>
            <span
              className="font-mono text-[11px] leading-[14px] text-text-tertiary"
              title="Текущее время относительно снимка T₀"
            >
              сейчас {elapsedLabel(run.t0, now)}
              {nowHours !== null && nowHours > AXIS_TO_H ? " ›" : ""}
            </span>
          </>
        ) : (
          <span className="font-serif text-[13px] leading-4 text-text-tertiary italic">
            прогноз не подключён
          </span>
        )}
      </div>
    </div>
  );
}

export function HorizonRail() {
  const horizonH = useWorkspaceStore((state) => state.forecastHorizonH);
  const sourcedRun = useForecastRun();
  const selected = useSelectedForecast();
  const now = useNow();
  const run = sourcedRun.origin === "none" ? null : sourcedRun.data;
  const isDemo = sourcedRun.origin === "demo";
  const forecast = selected.status === "ready" ? selected.forecast : null;

  return (
    <div className="grid h-full min-h-0 grid-cols-[var(--control-w)_minmax(0,1fr)]">
      <ControlBlock horizonH={horizonH} run={run} isDemo={isDemo} now={now} />
      <Tracks
        horizonH={horizonH}
        forecast={forecast}
        run={run}
        isDemo={isDemo}
        now={now}
        idleNote={run ? "Выберите пятно, чтобы построить прогноз" : "прогноз не подключён"}
      />
    </div>
  );
}
