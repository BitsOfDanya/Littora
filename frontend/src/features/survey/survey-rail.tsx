"use client";

import { useCallback } from "react";
import { DemoAction } from "@/features/cartouche/planned-group-note";
import { useHotkey } from "@/features/shell/hotkeys";
import { RailHeader } from "@/features/time-rail/rail-control-block";
import { IconButton } from "@/ui/button";
import { IconChevronLeft, IconChevronRight } from "@/ui/icons";
import { DAY_MS, stepDate, transitMinutes } from "./plan-model";
import { RankRing } from "./rank-ring";
import { formatDuration, formatKm, hhmm, windowLabel } from "./survey-copy";
import { useSurveyUiStore } from "./survey-ui-store";
import { type SurveyView, useSurveyView } from "./use-survey-view";

const PADDING_BEFORE_DAYS = 3;
const PADDING_AFTER_DAYS = 2;

export function useDepartureStepping(view: SurveyView | null) {
  const setDepartureDate = useSurveyUiStore((state) => state.setDepartureDate);
  const step = useCallback(
    (delta: number) => {
      if (view) setDepartureDate(stepDate(view.dates, view.departureDate, delta));
    },
    [view, setDepartureDate],
  );
  useHotkey("BracketLeft", () => step(-1), { enabled: Boolean(view) });
  useHotkey("BracketRight", () => step(1), { enabled: Boolean(view) });
  const index = view ? view.dates.indexOf(view.departureDate) : -1;
  return { step, canBack: index > 0, canForward: view ? index < view.dates.length - 1 : false };
}

function axisOf(view: SurveyView) {
  const start = Date.parse(`${view.plan.window.from}T00:00:00Z`) - PADDING_BEFORE_DAYS * DAY_MS;
  const end = Date.parse(`${view.plan.window.to}T00:00:00Z`) + (PADDING_AFTER_DAYS + 1) * DAY_MS;
  const ratio = (time: number) => `${((time - start) / (end - start)) * 100}%`;
  const days: number[] = [];
  for (let time = start; time <= end; time += DAY_MS) days.push(time);
  return { start, end, ratio, days };
}

function Tracks({ view }: { view: SurveyView }) {
  const axis = axisOf(view);
  const windowStart = Date.parse(`${view.plan.window.from}T00:00:00Z`);
  const windowEnd = Date.parse(`${view.plan.window.to}T00:00:00Z`) + DAY_MS;
  const departure = Date.parse(view.departure);
  const rankById = new Map(view.ranked.map((entry) => [entry.target.id, entry.rank]));
  return (
    <div className="grid h-full min-w-0 grid-cols-[92px_minmax(0,1fr)] grid-rows-[16px_22px_22px_minmax(0,1fr)] py-1.5 pr-3">
      <span />
      <div className="relative border-b border-line-hairline">
        {axis.days.map((time) => (
          <span
            key={time}
            style={{ left: axis.ratio(time) }}
            className="absolute top-0 h-full border-l border-line-hairline pl-1 font-mono text-[10.5px] leading-3 text-text-tertiary"
          >
            {new Date(time).toISOString().slice(8, 10)}.{new Date(time).toISOString().slice(5, 7)}
          </span>
        ))}
      </div>
      <span className="self-center text-[11px] text-text-tertiary">Окно выхода</span>
      <div className="relative">
        <span
          style={{
            left: axis.ratio(windowStart),
            width: `calc(${axis.ratio(windowEnd)} - ${axis.ratio(windowStart)})`,
          }}
          className="future-hatch absolute top-1 bottom-1 border-x-2 border-y border-text-primary"
          title={`Окно выхода ${windowLabel(view.plan.window.from, view.plan.window.to)}`}
        />
        <span
          style={{ left: axis.ratio(departure) }}
          className="absolute -top-5 -bottom-[46px] w-0 border-l-2 border-dashed border-accent-selection"
          title={`Выход ${view.departureDate} ${hhmm(view.departure)}`}
        />
      </div>
      <span className="self-center text-[11px] text-text-tertiary">Пролёты S2</span>
      <div className="relative">
        {view.plan.passes.map((pass) => (
          <span
            key={pass.id}
            style={{ left: axis.ratio(Date.parse(pass.acquiredAt)) }}
            title={`Плановый пролёт ${pass.acquiredAt.slice(0, 10)} ${hhmm(pass.acquiredAt)} · ${pass.platform}`}
            className="absolute top-1/2 size-2.5 -translate-x-1/2 -translate-y-1/2 border border-dashed border-text-secondary"
          />
        ))}
      </div>
      <span className="self-center text-[11px] text-text-tertiary">Цели · ETA</span>
      <div
        className="flex min-w-0 flex-wrap items-center gap-x-2.5 gap-y-1 overflow-hidden"
        style={{ paddingLeft: `max(0px, calc(${axis.ratio(departure)} - 8px))` }}
      >
        {view.route.stops.map((stop) => {
          const eta = view.eta.get(stop.targetId);
          return (
            <span
              key={stop.targetId}
              className="flex items-center gap-1 font-mono text-[11px] text-text-secondary"
            >
              <RankRing rank={rankById.get(stop.targetId) ?? stop.visit} size={16} />
              {eta ? hhmm(eta) : "—"}
            </span>
          );
        })}
      </div>
    </div>
  );
}

export function SurveyRail() {
  const view = useSurveyView();
  const stepping = useDepartureStepping(view);
  if (!view) {
    return (
      <div className="grid h-full grid-cols-[264px_minmax(0,1fr)]">
        <div className="flex flex-col justify-center gap-1.5 border-r border-line-hairline px-3">
          <RailHeader label="Окно выхода" sentence="план не подключён" demo={false} />
          <span className="text-[12px] text-text-secondary">
            Планирование обследований не подключено · survey_planning: planned
          </span>
          <DemoAction />
        </div>
        <div className="grid place-items-center text-[12px] text-text-tertiary">
          Окно выхода появится с планом обследования
        </div>
      </div>
    );
  }
  const minutes = transitMinutes(view.route.totalKm, view.plan.speedKn);
  return (
    <div className="grid h-full grid-cols-[264px_minmax(0,1fr)] max-xl:grid-cols-[240px_minmax(0,1fr)]">
      <div className="@container flex h-full min-w-0 flex-col justify-center gap-[3px] border-r border-line-hairline px-3 py-1.5">
        <RailHeader
          label="Окно выхода"
          sentence={windowLabel(view.plan.window.from, view.plan.window.to)}
          demo={view.isDemo}
        />
        <span className="font-mono text-[17px] leading-[22px] font-semibold whitespace-nowrap">
          {view.departureDate} {hhmm(view.departure)}
        </span>
        <span className="text-[11px] leading-[14px] text-text-tertiary">
          {view.plan.port.name} · {formatKm(view.route.totalKm)} · {formatDuration(minutes)}
        </span>
        <div className="flex items-center gap-1 pt-0.5">
          <IconButton
            label="Предыдущий день"
            shortcut="["
            size="sm"
            disabled={!stepping.canBack}
            onClick={() => stepping.step(-1)}
          >
            <IconChevronLeft />
          </IconButton>
          <IconButton
            label="Следующий день"
            shortcut="]"
            size="sm"
            disabled={!stepping.canForward}
            onClick={() => stepping.step(1)}
          >
            <IconChevronRight />
          </IconButton>
        </div>
      </div>
      <Tracks view={view} />
    </div>
  );
}

export function SurveyStepper() {
  const view = useSurveyView();
  const setDepartureDate = useSurveyUiStore((state) => state.setDepartureDate);
  if (!view)
    return <span className="text-[12px] text-text-tertiary">План обследования не подключён</span>;
  const index = view.dates.indexOf(view.departureDate);
  return (
    <div className="flex w-full items-center gap-2">
      <IconButton
        label="Предыдущий день"
        size="lg"
        disabled={index <= 0}
        onClick={() => setDepartureDate(stepDate(view.dates, view.departureDate, -1))}
      >
        <IconChevronLeft />
      </IconButton>
      <span className="flex-1 text-center font-mono text-[14px] font-medium">
        Выход {view.departureDate.slice(8, 10)}.{view.departureDate.slice(5, 7)}{" "}
        {hhmm(view.departure)}
      </span>
      <IconButton
        label="Следующий день"
        size="lg"
        disabled={index >= view.dates.length - 1}
        onClick={() => setDepartureDate(stepDate(view.dates, view.departureDate, 1))}
      >
        <IconChevronRight />
      </IconButton>
    </div>
  );
}
