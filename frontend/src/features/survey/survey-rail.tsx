"use client";

import { useCallback } from "react";
import type { SurveyState } from "@/data/survey";
import { DemoAction } from "@/features/cartouche/planned-group-note";
import { useHotkey } from "@/features/shell/hotkeys";
import { RailHeader } from "@/features/time-rail/rail-control-block";
import { Button, IconButton } from "@/ui/button";
import { cn } from "@/ui/cn";
import { IconChevronLeft, IconChevronRight } from "@/ui/icons";
import { DAY_MS, stepDate, transitMinutes } from "./plan-model";
import { RankRing } from "./rank-ring";
import {
  formatDuration,
  formatKm,
  hhmm,
  spanLabel,
  stampLabel,
  surveyStateCopy,
  windowLabel,
} from "./survey-copy";
import { planRequest, useSurveyUiStore } from "./survey-ui-store";
import { type SurveyView, useSurveyState, useSurveyView } from "./use-survey-view";

const PADDING_BEFORE_DAYS = 3;
const PADDING_AFTER_DAYS = 2;
const MAX_AXIS_DAYS = 12;

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

function dayStart(time: number): number {
  return Math.floor(time / DAY_MS) * DAY_MS;
}

function axisBounds(view: SurveyView): { start: number; end: number } {
  const exit = view.meta?.exitWindow;
  if (!view.meta) {
    return {
      start: Date.parse(`${view.plan.window.from}T00:00:00Z`) - PADDING_BEFORE_DAYS * DAY_MS,
      end: Date.parse(`${view.plan.window.to}T00:00:00Z`) + (PADDING_AFTER_DAYS + 1) * DAY_MS,
    };
  }
  const t0 = Date.parse(view.meta.t0);
  const start = dayStart(t0);
  const moments = [
    Date.parse(view.departure),
    ...(exit ? [Date.parse(exit.to)] : []),
    ...view.plan.passes.map((pass) => Date.parse(pass.acquiredAt)),
  ];
  const last = Math.max(...moments);
  const end = Math.min(dayStart(last) + 2 * DAY_MS, start + MAX_AXIS_DAYS * DAY_MS);
  return { start, end: Math.max(end, start + 3 * DAY_MS) };
}

function axisOf(view: SurveyView) {
  const { start, end } = axisBounds(view);
  const ratio = (time: number) => `${((time - start) / (end - start)) * 100}%`;
  const days: number[] = [];
  const last = view.meta ? end - DAY_MS : end;
  for (let time = start; time <= last; time += DAY_MS) days.push(time);
  return { start, end, ratio, days };
}

function windowSpan(view: SurveyView): { from: number; to: number; title: string } {
  const exit = view.meta?.exitWindow;
  if (exit)
    return {
      from: Date.parse(exit.from),
      to: Math.max(Date.parse(exit.to), Date.parse(exit.from) + 30 * 60_000),
      title: `Окно выхода ${spanLabel(exit.from, exit.to)}`,
    };
  return {
    from: Date.parse(`${view.plan.window.from}T00:00:00Z`),
    to: Date.parse(`${view.plan.window.to}T00:00:00Z`) + DAY_MS,
    title: `Окно выхода ${windowLabel(view.plan.window.from, view.plan.window.to)}`,
  };
}

function Tracks({ view }: { view: SurveyView }) {
  const axis = axisOf(view);
  const span = windowSpan(view);
  const departure = Date.parse(view.departure);
  const rankById = new Map(view.ranked.map((entry) => [entry.target.id, entry.rank]));
  const visible = (time: number) => time >= axis.start && time <= axis.end;
  const t0 = view.meta ? Date.parse(view.meta.t0) : null;
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
        {view.meta && !view.meta.exitWindow ? null : (
          <>
            <span
              style={{
                left: axis.ratio(span.from),
                width: `calc(${axis.ratio(span.to)} - ${axis.ratio(span.from)})`,
              }}
              className="future-hatch absolute top-1 bottom-1 border-x-2 border-y border-text-primary"
              title={span.title}
            />
            <span
              style={{ left: axis.ratio(departure) }}
              className="absolute -top-5 -bottom-[46px] w-0 border-l-2 border-dashed border-accent-selection"
              title={`Выход ${view.departureDate} ${hhmm(view.departure)}`}
            />
          </>
        )}
        {t0 !== null && visible(t0) ? (
          <span
            style={{ left: axis.ratio(t0) }}
            title={`Снимок ${view.meta ? stampLabel(view.meta.t0) : ""}`}
            className="absolute top-1 bottom-1 w-0 border-l border-text-secondary"
          />
        ) : null}
      </div>
      <span className="self-center text-[11px] text-text-tertiary">Пролёты S2</span>
      <div className="relative">
        {view.plan.passes
          .filter((pass) => visible(Date.parse(pass.acquiredAt)))
          .map((pass) => (
            <span
              key={pass.id}
              style={{ left: axis.ratio(Date.parse(pass.acquiredAt)) }}
              title={`${view.meta ? "Пролёт по каталогу" : "Плановый пролёт"} ${pass.acquiredAt.slice(0, 10)} ${hhmm(pass.acquiredAt)} · ${pass.platform}`}
              className={cn(
                "absolute top-1/2 size-2.5 -translate-x-1/2 -translate-y-1/2 border border-dashed border-text-secondary",
                view.meta && "border-solid",
              )}
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

function StateBlock({ state }: { state: SurveyState }) {
  const options = useSurveyUiStore((store) => store.options);
  const copy = surveyStateCopy(state);
  if (!copy) return null;
  return (
    <div className="grid h-full grid-cols-[264px_minmax(0,1fr)]">
      <div className="flex min-w-0 flex-col justify-center gap-1 border-r border-line-hairline px-3">
        <RailHeader label="Окно выхода" sentence="план не построен" demo={false} />
        <p className="truncate text-[13px] leading-4 text-text-primary">{copy.title}</p>
        <p
          className={cn(
            "truncate text-[11px] leading-[14px] text-text-tertiary",
            state.status === "failed" && "text-state-alarm",
          )}
          title={copy.detail}
        >
          {copy.detail}
        </p>
        {state.status === "absent" ? (
          <div>
            <Button variant="primary" size="sm" onClick={() => state.build(planRequest(options))}>
              Построить план
            </Button>
          </div>
        ) : null}
        {state.status === "failed" || state.status === "unavailable" ? (
          <div>
            <Button size="sm" onClick={state.retry}>
              Повторить
            </Button>
          </div>
        ) : null}
      </div>
      <div className="grid place-items-center text-[12px] text-text-tertiary">
        Окно выхода появится с планом обследования
      </div>
    </div>
  );
}

function PlannedBlock() {
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

function railSentence(view: SurveyView): string {
  const exit = view.meta?.exitWindow;
  if (!view.meta) return windowLabel(view.plan.window.from, view.plan.window.to);
  return exit ? spanLabel(exit.from, exit.to) : "окно не найдено";
}

export function SurveyRail() {
  const view = useSurveyView();
  const state = useSurveyState();
  const stepping = useDepartureStepping(view);
  if (!view) {
    if (state.status === "planned" || state.status === "demo") return <PlannedBlock />;
    return <StateBlock state={state} />;
  }
  const minutes = transitMinutes(view.route.totalKm, view.plan.speedKn);
  const noWindow = Boolean(view.meta && !view.meta.exitWindow);
  return (
    <div className="grid h-full grid-cols-[264px_minmax(0,1fr)] max-xl:grid-cols-[240px_minmax(0,1fr)]">
      <div className="@container flex h-full min-w-0 flex-col justify-center gap-[3px] border-r border-line-hairline px-3 py-1.5">
        <RailHeader label="Окно выхода" sentence={railSentence(view)} demo={view.isDemo} />
        <span className="font-mono text-[17px] leading-[22px] font-semibold whitespace-nowrap">
          {noWindow ? "окна нет" : `${view.departureDate} ${hhmm(view.departure)}`}
        </span>
        <span className="text-[11px] leading-[14px] text-text-tertiary">
          {view.plan.port
            ? `${view.plan.port.name} · ${formatKm(view.route.totalKm)} · ${formatDuration(minutes)}`
            : "порт не найден — маршрут не строится"}
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
          {view.meta?.exitWindow?.past ? (
            <span className="ml-1 text-[11px] text-text-tertiary">окно в прошлом</span>
          ) : null}
        </div>
      </div>
      <Tracks view={view} />
    </div>
  );
}

export function SurveyStepper() {
  const view = useSurveyView();
  const state = useSurveyState();
  const setDepartureDate = useSurveyUiStore((store) => store.setDepartureDate);
  if (!view) {
    const copy = surveyStateCopy(state);
    return (
      <span className="text-[12px] text-text-tertiary">
        {copy ? copy.title : "План обследования не подключён"}
      </span>
    );
  }
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
