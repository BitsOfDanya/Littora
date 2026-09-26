"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { findAoi } from "@/config/aois";
import { WORKSPACE_MODES } from "@/config/modes";
import type { SurveyPlanMeta, SurveyPlanTarget, SurveyState } from "@/data/survey";
import { useAdoptSavedAnalysis } from "@/features/analysis/use-analysis";
import { DemoAction } from "@/features/cartouche/planned-group-note";
import type { Crumb } from "@/features/inspector/parts/breadcrumbs";
import { InspectorFrame } from "@/features/inspector/parts/inspector-frame";
import { easeToIfOutside, fitAoi } from "@/features/map/camera";
import { useMainMap } from "@/features/map/use-main-map";
import { useSurveyPlanStore } from "@/features/monitor/survey-plan-store";
import { modeHref, useViewQuery } from "@/features/shell/orientation/modes";
import { countRu, type PluralForms } from "@/features/shell/orientation/plural";
import { ShellSlot } from "@/features/shell/shell-slots";
import { formatLngLat } from "@/lib/format/coordinates";
import { formatArea, formatNumber } from "@/lib/format/numbers";
import { useAnalysisStore } from "@/state/analysis-store";
import { usePreferencesStore } from "@/state/preferences-store";
import { useWorkspaceStore } from "@/state/workspace-store";
import { Button, buttonClasses } from "@/ui/button";
import { cn } from "@/ui/cn";
import { DemoTag } from "@/ui/demo-mark";
import { IconDownload } from "@/ui/icons";
import { KeyValue, KeyValueList } from "@/ui/key-value";
import { PlannedState, PlannedTag } from "@/ui/planned";
import { PanelSection } from "@/ui/section";
import { Segmented } from "@/ui/segmented";
import { ComponentBars, componentsAriaLabel } from "./component-bars";
import {
  bearingDeg,
  compassPoint,
  distanceKm,
  type GpxPoint,
  nextPassFor,
  type RankedTarget,
  selectedTargetOf,
  toGpx,
  transitMinutes,
} from "./plan-model";
import { RankRing } from "./rank-ring";
import {
  API_RANKING_RULE,
  DRIFT_HINT,
  elapsedLabel,
  formatDuration,
  formatHoursShort,
  formatKm,
  formatScore,
  hhmm,
  METHOD_LABELS,
  PLAN_NOTE,
  RANKING_RULE,
  ROUTE_TARGET_OPTIONS,
  SPEED_OPTIONS_KN,
  spanLabel,
  stampLabel,
  surveyStateCopy,
  targetsWord,
  UAV_RANGE_OPTIONS_KM,
  URGENCY_LABELS,
  windowLabel,
} from "./survey-copy";
import {
  planRequest,
  SURVEY_OUTCOMES,
  type SurveyOutcome,
  type SurveyPlanOptions,
  useSurveyUiStore,
} from "./survey-ui-store";
import { type SurveyView, useSurveyState, useSurveyView } from "./use-survey-view";

const MONITOR_MODE = WORKSPACE_MODES[0];
const FORECAST_MODE = WORKSPACE_MODES[2];
const ZONE_FORMS: PluralForms = ["зона", "зоны", "зон"];

export function PlanTag({ className }: { className?: string }) {
  return (
    <span
      title={PLAN_NOTE}
      className={cn(
        "inline-flex h-[18px] shrink-0 items-center rounded-[var(--radius-ctl)] border border-line-control px-1 font-mono text-[11px] leading-none text-text-secondary",
        className,
      )}
    >
      расчёт
    </span>
  );
}

function TargetRow({
  entry,
  selected,
  onSelect,
}: {
  entry: RankedTarget;
  selected: boolean;
  onSelect: () => void;
}) {
  const { target, rank, score } = entry;
  return (
    <li>
      <button
        type="button"
        onClick={onSelect}
        aria-pressed={selected}
        aria-label={`Цель ${rank}, ${target.id}, пятно ${target.candidateId}, балл ${formatScore(score)}. ${target.reason}. ${componentsAriaLabel(target.components)}`}
        className={cn(
          "flex w-full flex-col gap-1.5 border-b border-line-hairline px-4 py-2.5 text-left hover:bg-surface-raised",
          selected &&
            "border-l-[3px] border-l-accent-selection bg-accent-selection-wash pl-[13px] hover:bg-accent-selection-wash",
        )}
      >
        <span className="flex items-center gap-2">
          <RankRing rank={rank} selected={selected} />
          <span className="font-mono text-[13px] font-medium">
            {target.id} · {target.candidateId}
          </span>
          <span className="ml-auto font-mono text-[15px] font-medium">{formatScore(score)}</span>
        </span>
        <span className="text-[12px] leading-4 text-text-secondary">{target.reason}</span>
        <ComponentBars components={target.components} />
      </button>
    </li>
  );
}

function WhereToSearch({ view, targetId }: { view: SurveyView; targetId: string }) {
  const format = usePreferencesStore((state) => state.coordinateFormat);
  const target = view.plan.targets.find((entry) => entry.id === targetId);
  const state = view.drift.get(targetId);
  const stop = view.route.stops.find((entry) => entry.targetId === targetId);
  if (!target || !state) return null;
  const course = compassPoint(bearingDeg(target.observedPosition, state.position));
  const port = view.plan.port;
  const fromPortKm = stop?.cumKm ?? (port ? distanceKm(port.position, state.position) : null);
  const pass = nextPassFor(view.plan.passes, state.position, view.plan.issuedAt, view.departure);
  const eta = view.eta.get(targetId);
  const shift = target.track
    ? `${formatKm(state.shiftKm)} ${course} за ${elapsedLabel(state.days)}`
    : `${formatKm(state.shiftKm)} ${course} за ${Math.round(state.days)} сут`;
  return (
    <PanelSection title="Где искать сейчас" aside={view.isDemo ? <DemoTag /> : <PlanTag />}>
      <KeyValueList>
        <KeyValue label="Ожидаемое положение">
          {formatLngLat(state.position, format === "dms" ? "dm" : format)}
        </KeyValue>
        <KeyValue label="Сдвиг с момента снимка">
          {view.isDemo || target.track ? shift : "дрейф не рассчитан"}
        </KeyValue>
        <KeyValue label="Радиус поиска">{formatKm(state.radiusKm)}</KeyValue>
        {port && fromPortKm !== null ? (
          <KeyValue label={`От порта ${port.name}`}>
            {formatKm(fromPortKm)} · {formatDuration(transitMinutes(fromPortKm, view.plan.speedKn))}{" "}
            при {view.plan.speedKn} уз
          </KeyValue>
        ) : null}
        {eta ? <KeyValue label="Прибытие по маршруту">{hhmm(eta)}</KeyValue> : null}
        <KeyValue label="Метод проверки">{METHOD_LABELS[target.method]}</KeyValue>
        <KeyValue label="Следующий пролёт S2">
          {pass
            ? `${pass.pass.acquiredAt.slice(0, 10)} ${hhmm(pass.pass.acquiredAt)} · ${pass.pass.platform}`
            : "нет в окне"}
        </KeyValue>
      </KeyValueList>
      {pass ? (
        <p className="text-[12px] text-text-tertiary">
          {pass.beforeDeparture
            ? "Пролёт до выхода — сверить снимок перед отправкой."
            : "Пролёт после выхода — сверить с результатом проверки."}
        </p>
      ) : null}
    </PanelSection>
  );
}

function uavText(feasible: boolean | null): string {
  if (feasible === null) return "не оценено";
  return feasible ? "в радиусе" : "вне радиуса";
}

function BulletList({ items, label }: { items: readonly string[]; label: string }) {
  return (
    <ul aria-label={label} className="flex flex-col gap-1">
      {items.map((item) => (
        <li key={item} className="flex gap-2 text-[12px] leading-4 text-text-secondary">
          <span aria-hidden className="text-text-tertiary">
            —
          </span>
          <span>{item}</span>
        </li>
      ))}
    </ul>
  );
}

function TargetBrief({ target }: { target: SurveyPlanTarget }) {
  const details = target.details;
  if (!details) return null;
  const { urgency } = details;
  return (
    <>
      <PanelSection title="Зачем и насколько срочно" aside={<PlanTag />}>
        <KeyValueList>
          <KeyValue label="Срочность">{URGENCY_LABELS[urgency.level]}</KeyValue>
          <KeyValue label="Уход на 1 / 2 км">
            {urgency.leaves1kmH === null && urgency.leaves2kmH === null
              ? urgency.level === "unknown"
                ? "не оценён"
                : "не уходит"
              : `${urgency.leaves1kmH === null ? "—" : formatHoursShort(urgency.leaves1kmH)} / ${
                  urgency.leaves2kmH === null ? "—" : formatHoursShort(urgency.leaves2kmH)
                }`}
          </KeyValue>
          {urgency.beaching ? (
            <KeyValue label="Вынос на берег">
              +{urgency.beaching.windowH[0]}…{urgency.beaching.windowH[1]} ч · p ={" "}
              {formatNumber(urgency.beaching.probability, 2)}
            </KeyValue>
          ) : null}
          <KeyValue label="Окно проверки">
            {details.window ? spanLabel(details.window.from, details.window.to) : "нет"}
          </KeyValue>
          {details.spotUntil ? (
            <KeyValue label="В пределах 2 км до">{stampLabel(details.spotUntil)}</KeyValue>
          ) : null}
          {details.shiftAtEtaKm !== null ? (
            <KeyValue label="Смещение к прибытию">{formatKm(details.shiftAtEtaKm)}</KeyValue>
          ) : null}
          <KeyValue label="Площадь">
            {formatArea(details.areaKm2 * 1e6)} · {countRu(details.zoneIds.length, ZONE_FORMS)}
          </KeyValue>
          <KeyValue label="До берега">
            {details.shoreKm === null ? "не оценено" : formatKm(details.shoreKm)}
          </KeyValue>
          {details.nearestPort ? (
            <KeyValue label="Ближайший порт от места снимка">
              {details.nearestPort.name} · {formatKm(details.nearestPort.distanceKm)}
            </KeyValue>
          ) : null}
          <KeyValue label={`БПЛА ≤ ${formatNumber(details.uav.rangeKm)} км`}>
            {uavText(details.uav.feasible)}
          </KeyValue>
        </KeyValueList>
        <p className="text-[12px] leading-4 text-text-tertiary">
          {details.window ? details.window.basis : details.windowNote}
          {details.uav.basis ? ` · БПЛА: ${details.uav.basis}` : null}
        </p>
      </PanelSection>
      <PanelSection title="Почему в плане">
        <BulletList items={details.why} label={`Основания цели ${target.id}`} />
      </PanelSection>
      <PanelSection title="Что даст проверка">
        <BulletList items={details.checks} label={`Что даст проверка цели ${target.id}`} />
      </PanelSection>
    </>
  );
}

function OutcomeForm({ targetId, isDemo }: { targetId: string; isDemo: boolean }) {
  const saved = useSurveyUiStore((state) => state.outcomes[targetId]);
  const saveOutcome = useSurveyUiStore((state) => state.saveOutcome);
  const [draft, setDraft] = useState<SurveyOutcome | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const value = draft ?? saved ?? "not_checked";
  return (
    <PanelSection
      title="Результат проверки"
      aside={
        isDemo ? (
          <DemoTag title="Сохраняется только в этой вкладке браузера" />
        ) : (
          <span className="text-[11px] text-text-tertiary">только в этой вкладке</span>
        )
      }
    >
      <fieldset className="flex flex-col gap-1">
        <legend className="sr-only">Результат проверки цели {targetId}</legend>
        {SURVEY_OUTCOMES.map((outcome) => (
          <label
            key={outcome.value}
            className="flex min-h-7 cursor-pointer items-center gap-2.5 text-[13px]"
          >
            <input
              type="radio"
              name={`outcome-${targetId}`}
              value={outcome.value}
              checked={value === outcome.value}
              onChange={() => {
                setDraft(outcome.value);
                setConfirmed(false);
              }}
              className="size-4 accent-[var(--primary-fill)]"
            />
            {outcome.label}
          </label>
        ))}
      </fieldset>
      <div>
        <Button
          onClick={() => {
            saveOutcome(targetId, value);
            setConfirmed(true);
            window.setTimeout(() => setConfirmed(false), 1200);
          }}
        >
          {confirmed ? "Сохранено" : "Сохранить результат"}
        </Button>
      </div>
    </PanelSection>
  );
}

function DateButtons({ view }: { view: SurveyView }) {
  const setDepartureDate = useSurveyUiStore((state) => state.setDepartureDate);
  return (
    <div role="radiogroup" aria-label="День выхода" className="flex flex-wrap gap-1">
      {view.dates.map((date) => (
        <button
          key={date}
          type="button"
          role="radio"
          aria-checked={date === view.departureDate}
          onClick={() => setDepartureDate(date)}
          className={cn(
            "h-7 rounded-[var(--radius-ctl)] border border-line-control px-2 font-mono text-[12px] text-text-secondary hover:text-text-primary",
            date === view.departureDate &&
              "border-accent-selection bg-accent-selection text-surface-panel hover:text-surface-panel",
          )}
        >
          {date.slice(8, 10)}.{date.slice(5, 7)}
        </button>
      ))}
    </div>
  );
}

function DepartureBlock({ view }: { view: SurveyView }) {
  return (
    <PanelSection title="Выход">
      <KeyValueList>
        <KeyValue label="Порт">{view.plan.port?.name ?? "не найден"}</KeyValue>
        <KeyValue label="Выход">{`${view.departureDate} ${hhmm(view.departure)}`}</KeyValue>
        <KeyValue label="Маршрут">{formatKm(view.route.totalKm)}</KeyValue>
        <KeyValue label="В пути">
          {formatDuration(transitMinutes(view.route.totalKm, view.plan.speedKn))} при{" "}
          {view.plan.speedKn} уз
        </KeyValue>
        <KeyValue label="Окно выхода">
          {windowLabel(view.plan.window.from, view.plan.window.to)}
        </KeyValue>
      </KeyValueList>
      <DateButtons view={view} />
    </PanelSection>
  );
}

function ExitWindowBlock({ view, meta }: { view: SurveyView; meta: SurveyPlanMeta }) {
  const exit = meta.exitWindow;
  const viewQuery = useViewQuery();
  return (
    <PanelSection title="Окно выхода" aside={<PlanTag />}>
      <KeyValueList>
        <KeyValue label="Порт">{view.plan.port?.name ?? "не найден"}</KeyValue>
        {exit ? (
          <KeyValue label="Выход">{`${view.departureDate} ${hhmm(view.departure)}`}</KeyValue>
        ) : null}
        <KeyValue label="Окно выхода">
          {exit ? spanLabel(exit.from, exit.to) : "не найдено"}
        </KeyValue>
        {exit ? (
          <KeyValue label="Светлое время">{spanLabel(exit.daylight[0], exit.daylight[1])}</KeyValue>
        ) : null}
        {exit?.beachingAt ? (
          <KeyValue label="Первый вынос на берег">{stampLabel(exit.beachingAt)}</KeyValue>
        ) : exit?.scenarioEnd ? (
          <KeyValue label="Конец сценария дрейфа">{stampLabel(exit.scenarioEnd)}</KeyValue>
        ) : null}
        <KeyValue label="Готовность снимка">{stampLabel(meta.readyAt)}</KeyValue>
        {view.plan.port ? (
          <>
            <KeyValue label="Маршрут с возвратом">{formatKm(view.route.totalKm)}</KeyValue>
            <KeyValue label="В пути">
              {formatDuration(transitMinutes(view.route.totalKm, view.plan.speedKn))} при{" "}
              {view.plan.speedKn} уз + {view.plan.dwellMin} мин на цель
            </KeyValue>
          </>
        ) : null}
      </KeyValueList>
      {view.dates.length > 1 ? <DateButtons view={view} /> : null}
      {exit ? <p className="text-[12px] leading-4 text-text-tertiary">{exit.basis}</p> : null}
      {exit?.past ? (
        <p className="text-[12px] leading-4 text-text-secondary">
          Окно в прошлом: план показывает, как следовало выйти после снимка {stampLabel(meta.t0)}.
        </p>
      ) : null}
      {!meta.drift.used ? (
        <p className="text-[12px] leading-4 text-text-secondary">
          {DRIFT_HINT}{" "}
          <Link href={modeHref(FORECAST_MODE, viewQuery)} className="underline underline-offset-2">
            Открыть прогноз
          </Link>
        </p>
      ) : null}
    </PanelSection>
  );
}

function OptionsBlock({
  options,
  onChange,
  disabled,
}: {
  options: SurveyPlanOptions;
  onChange: (options: SurveyPlanOptions) => void;
  disabled?: boolean;
}) {
  const choose = <K extends keyof SurveyPlanOptions>(key: K, value: string) =>
    onChange({ ...options, [key]: Number(value) });
  return (
    <PanelSection title="Параметры плана">
      <div className="flex flex-col gap-2 text-[12px] text-text-secondary">
        <div className="flex items-center justify-between gap-2">
          <span>Скорость судна, уз</span>
          <Segmented
            label="Скорость судна"
            value={String(options.speedKn)}
            options={SPEED_OPTIONS_KN.map((value) => ({
              value: String(value),
              label: String(value),
              disabled,
            }))}
            onChange={(value) => choose("speedKn", value)}
          />
        </div>
        <div className="flex items-center justify-between gap-2">
          <span>Радиус БПЛА, км</span>
          <Segmented
            label="Радиус БПЛА"
            value={String(options.uavRangeKm)}
            options={UAV_RANGE_OPTIONS_KM.map((value) => ({
              value: String(value),
              label: String(value),
              disabled,
            }))}
            onChange={(value) => choose("uavRangeKm", value)}
          />
        </div>
        <div className="flex items-center justify-between gap-2">
          <span>Целей в маршруте</span>
          <Segmented
            label="Целей в маршруте"
            value={String(options.routeTargets)}
            options={ROUTE_TARGET_OPTIONS.map((value) => ({
              value: String(value),
              label: String(value),
              disabled,
            }))}
            onChange={(value) => choose("routeTargets", value)}
          />
        </div>
      </div>
    </PanelSection>
  );
}

function PlanBasis({ meta }: { meta: SurveyPlanMeta }) {
  const notes = [meta.reason, meta.drift.used ? meta.drift.note : null, ...meta.messages].filter(
    (note): note is string => Boolean(note),
  );
  return (
    <PanelSection title="Основания плана">
      <BulletList items={[...new Set(notes)]} label="Основания и ограничения плана" />
      <p className="font-mono text-[11px] leading-[14px] text-text-tertiary">
        анализ {meta.analysisId} · зон {meta.zones.total} · групп {meta.zones.groups} · в плане{" "}
        {meta.zones.planned}
        {meta.port ? ` · порты: ${meta.port.source}` : ""}
      </p>
    </PanelSection>
  );
}

function OperatorAdditions({ planned }: { planned: boolean }) {
  const entries = useSurveyPlanStore((state) => state.entries);
  const remove = useSurveyPlanStore((state) => state.remove);
  if (!entries.length) return null;
  return (
    <PanelSection title="Добавлено из досье">
      <ul className="flex flex-col">
        {entries.map((entry) => (
          <li
            key={entry.candidateId}
            className="flex min-h-7 items-center gap-2 border-b border-line-hairline last:border-b-0"
          >
            <span className="font-mono text-[13px]">{entry.candidateId}</span>
            <span className="text-[12px] text-text-tertiary">
              {hhmm(entry.addedAt)} · {entry.actor} ·{" "}
              {planned
                ? "вне расчёта: план строится по зонам анализа"
                : "балл появится с survey_planning"}
            </span>
            <Button
              variant="quiet"
              size="sm"
              className="ml-auto"
              onClick={() => remove(entry.candidateId)}
            >
              Убрать
            </Button>
          </li>
        ))}
      </ul>
    </PanelSection>
  );
}

function gpxHref(view: SurveyView): string | null {
  const port = view.plan.port;
  if (!port || !view.route.stops.length) return null;
  const points: GpxPoint[] = [{ name: port.name, position: port.berth, note: "порт выхода" }];
  for (const stop of view.route.stops) {
    const target = view.plan.targets.find((entry) => entry.id === stop.targetId);
    const position = view.route.path[stop.vertex];
    const eta = view.eta.get(stop.targetId);
    if (target && position)
      points.push({
        name: target.id,
        position,
        note: `${target.reason}${eta ? ` · прибытие ${hhmm(eta)}` : ""}`,
      });
  }
  points.push({ name: port.name, position: port.berth, note: "возврат" });
  const gpx = toGpx(`Littora · план обследования · ${view.departureDate}`, points);
  return `data:application/gpx+xml;charset=utf-8,${encodeURIComponent(gpx)}`;
}

function ApiFooter({ view, state }: { view: SurveyView; state: SurveyState }) {
  const href = useMemo(() => gpxHref(view), [view]);
  const options = useSurveyUiStore((store) => store.options);
  const ready = state.status === "ready" ? state : null;
  return (
    <>
      {href ? (
        <a
          className={buttonClasses("default", "lg")}
          href={href}
          download={`littora-survey-${view.meta?.analysisId ?? "plan"}-${view.departureDate}.gpx`}
        >
          <IconDownload size={14} />
          Маршрут GPX
        </a>
      ) : (
        <Button size="lg" disabled icon={<IconDownload size={14} />} title="Маршрута нет">
          Маршрут GPX
        </Button>
      )}
      <Button
        size="lg"
        busy={ready?.busy}
        disabled={!ready || ready.busy}
        onClick={() => ready?.rebuild(planRequest(options))}
      >
        {ready?.busy ? "Перестраиваем…" : "Перестроить план"}
      </Button>
    </>
  );
}

function ReadyPanel({ view, state }: { view: SurveyView; state: SurveyState }) {
  const map = useMainMap();
  const aoi = findAoi(useWorkspaceStore((store) => store.aoiId));
  const rawSelectedId = useWorkspaceStore((store) => store.selectedTargetId);
  const zoneId = useWorkspaceStore((store) => store.selectedCandidateId);
  const selectedId = selectedTargetOf(view.plan.targets, rawSelectedId, zoneId);
  const selectTarget = useWorkspaceStore((store) => store.selectTarget);
  const setOptions = useSurveyUiStore((store) => store.setOptions);
  const meta = view.meta;
  const crumbs = useMemo<Crumb[]>(
    () => [
      {
        label: aoi?.name ?? "Район",
        serif: true,
        onSelect: map && aoi ? () => fitAoi(map, aoi) : undefined,
      },
      { label: `окно ${windowLabel(view.plan.window.from, view.plan.window.to)}` },
      { label: selectedId ?? "План" },
    ],
    [aoi, map, view.plan.window, selectedId],
  );
  const count = view.ranked.length;
  const select = (entry: RankedTarget) => {
    selectTarget(entry.target.id);
    const position = view.drift.get(entry.target.id)?.position;
    if (map && position) easeToIfOutside(map, position);
  };
  const selected = view.plan.targets.find((target) => target.id === selectedId) ?? null;
  const ready = state.status === "ready" ? state : null;
  const changeOptions = (options: SurveyPlanOptions) => {
    setOptions(options);
    ready?.rebuild(planRequest(options));
  };

  return (
    <InspectorFrame
      label="План обследования"
      eyebrow={
        meta && !meta.exitWindow
          ? `План обследования · снимок ${stampLabel(meta.t0)} · без маршрута`
          : `План обследования · на ${view.departureDate} · выход ${hhmm(view.departure)}`
      }
      crumbs={crumbs}
      demoSource={view.isDemo ? "demo/survey.ts" : null}
      header={
        <>
          <h2
            className={cn(
              "font-serif text-[20px] leading-6 italic",
              meta && "flex items-center gap-2",
            )}
          >
            {count} {targetsWord(count)} · {meta && !meta.route ? "без маршрута" : "1 выход"}
            {meta ? <PlanTag className="not-italic" /> : null}
          </h2>
          <p className="text-[12px] leading-4 text-text-secondary">
            {meta ? API_RANKING_RULE : RANKING_RULE}
          </p>
          {meta ? (
            <p className="text-[12px] leading-4 text-text-tertiary">
              {meta.label} · снимок {stampLabel(meta.t0)}
            </p>
          ) : null}
        </>
      }
      footer={
        meta ? (
          <ApiFooter view={view} state={state} />
        ) : (
          <>
            <Button disabled title="Экспорт появится с survey_planning">
              Маршрут GPX <PlannedTag capability="survey_planning" />
            </Button>
            <Button disabled title="Бриф появится с survey_planning">
              Сформировать бриф… <PlannedTag capability="survey_planning" />
            </Button>
          </>
        )
      }
    >
      <ol aria-label="Цели по убыванию балла">
        {view.ranked.map((entry) => (
          <TargetRow
            key={entry.target.id}
            entry={entry}
            selected={entry.target.id === selectedId}
            onSelect={() => select(entry)}
          />
        ))}
      </ol>
      {selectedId ? <WhereToSearch view={view} targetId={selectedId} /> : null}
      {selected ? <TargetBrief target={selected} /> : null}
      {meta ? <ExitWindowBlock view={view} meta={meta} /> : <DepartureBlock view={view} />}
      {meta ? (
        <OptionsBlock
          options={{
            speedKn: meta.options.speedKn,
            uavRangeKm: meta.options.uavRangeKm,
            routeTargets: meta.options.routeTargets,
          }}
          onChange={changeOptions}
          disabled={ready?.busy}
        />
      ) : null}
      {selectedId ? <OutcomeForm targetId={selectedId} isDemo={view.isDemo} /> : null}
      {meta ? <PlanBasis meta={meta} /> : null}
      <OperatorAdditions planned={Boolean(meta)} />
    </InspectorFrame>
  );
}

function StateAction({ state }: { state: SurveyState }) {
  const viewQuery = useViewQuery();
  const options = useSurveyUiStore((store) => store.options);
  switch (state.status) {
    case "absent":
      return (
        <Button variant="primary" onClick={() => state.build(planRequest(options))}>
          Построить план
        </Button>
      );
    case "building":
      return (
        <Button variant="primary" busy disabled>
          Строим…
        </Button>
      );
    case "failed":
    case "unavailable":
      return <Button onClick={state.retry}>Повторить</Button>;
    case "no-analysis":
    case "no-zones":
      return (
        <Link href={modeHref(MONITOR_MODE, viewQuery)} className={buttonClasses("default", "md")}>
          Открыть мониторинг
        </Link>
      );
    default:
      return null;
  }
}

function SurveyStatePanel({ state }: { state: SurveyState }) {
  const viewQuery = useViewQuery();
  const options = useSurveyUiStore((store) => store.options);
  const setOptions = useSurveyUiStore((store) => store.setOptions);
  const copy = surveyStateCopy(state);
  if (!copy) return null;
  return (
    <div className="flex flex-col">
      <section className="flex flex-col gap-2 p-4" aria-live="polite">
        <h3 className="text-[13px] font-semibold text-text-primary">{copy.title}</h3>
        <p
          className={cn(
            "text-[13px] text-text-secondary",
            state.status === "failed" && "text-state-alarm",
          )}
        >
          {copy.detail}
        </p>
        {state.status === "absent" ? (
          <p className="text-[12px] leading-4 text-text-tertiary">
            {state.driftReady ? (
              "Сценарий дрейфа рассчитан — в плане будут срочность и окна по времени."
            ) : (
              <>
                {DRIFT_HINT}{" "}
                <Link
                  href={modeHref(FORECAST_MODE, viewQuery)}
                  className="underline underline-offset-2"
                >
                  Открыть прогноз
                </Link>
              </>
            )}
          </p>
        ) : null}
        <p className="text-[11px] leading-4 text-text-tertiary">Результат — {PLAN_NOTE}.</p>
        <div className="pt-1">
          <StateAction state={state} />
        </div>
      </section>
      {state.status === "absent" ? <OptionsBlock options={options} onChange={setOptions} /> : null}
    </div>
  );
}

function PlannedPanel() {
  return (
    <div className="flex flex-col gap-3 p-4">
      <PlannedState
        title="Планирование обследований — не подключено"
        capability="survey_planning"
        requirement="детекция, прогноз дрейфа и данные о порте и судне."
        action={<DemoAction />}
      >
        Ранжированный список участков для проверки с судна или БПЛА: зачем, насколько срочно и что
        это даст.
      </PlannedState>
      <p className="text-[12px] text-text-tertiary">
        План пуст. Добавьте пятно из досье — кнопка «В план обследования».
      </p>
    </div>
  );
}

function useAutoBuild(state: SurveyState) {
  const analysisId = useAnalysisStore((store) => store.analysisId);
  const options = useSurveyUiStore((store) => store.options);
  const builtRef = useRef<string | null>(null);
  useEffect(() => {
    if (state.status !== "absent" || !analysisId || builtRef.current === analysisId) return;
    builtRef.current = analysisId;
    state.build(planRequest(options));
  }, [state, analysisId, options]);
}

export function SurveyPanel() {
  const view = useSurveyView();
  const state = useSurveyState();
  useAdoptSavedAnalysis();
  useAutoBuild(state);
  return (
    <ShellSlot region="inspector">
      {view ? (
        <ReadyPanel view={view} state={state} />
      ) : state.status === "planned" || state.status === "demo" ? (
        <PlannedPanel />
      ) : (
        <SurveyStatePanel state={state} />
      )}
    </ShellSlot>
  );
}
