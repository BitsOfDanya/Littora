"use client";

import { useMemo, useState } from "react";
import { findAoi } from "@/config/aois";
import { DemoAction } from "@/features/cartouche/planned-group-note";
import type { Crumb } from "@/features/inspector/parts/breadcrumbs";
import { InspectorFrame } from "@/features/inspector/parts/inspector-frame";
import { easeToIfOutside, fitAoi } from "@/features/map/camera";
import { useMainMap } from "@/features/map/use-main-map";
import { useSurveyPlanStore } from "@/features/monitor/survey-plan-store";
import { ShellSlot } from "@/features/shell/shell-slots";
import { formatLngLat } from "@/lib/format/coordinates";
import { usePreferencesStore } from "@/state/preferences-store";
import { useWorkspaceStore } from "@/state/workspace-store";
import { Button } from "@/ui/button";
import { cn } from "@/ui/cn";
import { DemoTag } from "@/ui/demo-mark";
import { KeyValue, KeyValueList } from "@/ui/key-value";
import { PlannedState, PlannedTag } from "@/ui/planned";
import { PanelSection } from "@/ui/section";
import { ComponentBars, componentsAriaLabel } from "./component-bars";
import {
  bearingDeg,
  compassPoint,
  distanceKm,
  nextPassFor,
  type RankedTarget,
  transitMinutes,
} from "./plan-model";
import { RankRing } from "./rank-ring";
import {
  formatDuration,
  formatKm,
  formatScore,
  hhmm,
  METHOD_LABELS,
  RANKING_RULE,
  targetsWord,
  windowLabel,
} from "./survey-copy";
import { SURVEY_OUTCOMES, type SurveyOutcome, useSurveyUiStore } from "./survey-ui-store";
import { type SurveyView, useSurveyView } from "./use-survey-view";

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
  const fromPortKm = stop?.cumKm ?? distanceKm(view.plan.port.position, state.position);
  const pass = nextPassFor(view.plan.passes, state.position, view.plan.issuedAt, view.departure);
  const eta = view.eta.get(targetId);
  return (
    <PanelSection title="Где искать сейчас" aside={<DemoTag />}>
      <KeyValueList>
        <KeyValue label="Ожидаемое положение">
          {formatLngLat(state.position, format === "dms" ? "dm" : format)}
        </KeyValue>
        <KeyValue label="Сдвиг с момента снимка">
          {formatKm(state.shiftKm)} {course} за {Math.round(state.days)} сут
        </KeyValue>
        <KeyValue label="Радиус поиска">{formatKm(state.radiusKm)}</KeyValue>
        <KeyValue label={`От порта ${view.plan.port.name}`}>
          {formatKm(fromPortKm)} · {formatDuration(transitMinutes(fromPortKm, view.plan.speedKn))}{" "}
          при {view.plan.speedKn} уз
        </KeyValue>
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

function OutcomeForm({ targetId }: { targetId: string }) {
  const saved = useSurveyUiStore((state) => state.outcomes[targetId]);
  const saveOutcome = useSurveyUiStore((state) => state.saveOutcome);
  const [draft, setDraft] = useState<SurveyOutcome | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const value = draft ?? saved ?? "not_checked";
  return (
    <PanelSection
      title="Результат проверки"
      aside={<DemoTag title="Сохраняется только в этой вкладке браузера" />}
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

function DepartureBlock({ view }: { view: SurveyView }) {
  const setDepartureDate = useSurveyUiStore((state) => state.setDepartureDate);
  return (
    <PanelSection title="Выход">
      <KeyValueList>
        <KeyValue label="Порт">{view.plan.port.name}</KeyValue>
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
    </PanelSection>
  );
}

function OperatorAdditions() {
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
              {hhmm(entry.addedAt)} · {entry.actor} · балл появится с survey_planning
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

function ReadyPanel({ view }: { view: SurveyView }) {
  const map = useMainMap();
  const aoi = findAoi(useWorkspaceStore((state) => state.aoiId));
  const selectedId = useWorkspaceStore((state) => state.selectedTargetId);
  const selectTarget = useWorkspaceStore((state) => state.selectTarget);
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

  return (
    <InspectorFrame
      label="План обследования"
      eyebrow={`План обследования · на ${view.departureDate} · выход ${hhmm(view.departure)}`}
      crumbs={crumbs}
      demoSource={view.isDemo ? "demo/survey.ts" : null}
      header={
        <>
          <h2 className="font-serif text-[20px] leading-6 italic">
            {count} {targetsWord(count)} · 1 выход
          </h2>
          <p className="text-[12px] leading-4 text-text-secondary">{RANKING_RULE}</p>
        </>
      }
      footer={
        <>
          <Button disabled title="Экспорт появится с survey_planning">
            Маршрут GPX <PlannedTag capability="survey_planning" />
          </Button>
          <Button disabled title="Бриф появится с survey_planning">
            Сформировать бриф… <PlannedTag capability="survey_planning" />
          </Button>
        </>
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
      <DepartureBlock view={view} />
      {selectedId ? <OutcomeForm targetId={selectedId} /> : null}
      <OperatorAdditions />
    </InspectorFrame>
  );
}

export function SurveyPanel() {
  const view = useSurveyView();
  return (
    <ShellSlot region="inspector">
      {view ? (
        <ReadyPanel view={view} />
      ) : (
        <div className="flex flex-col gap-3 p-4">
          <PlannedState
            title="Планирование обследований — не подключено"
            capability="survey_planning"
            requirement="детекция, прогноз дрейфа и данные о порте и судне."
            action={<DemoAction />}
          >
            Ранжированный список участков для проверки с судна или БПЛА: зачем, насколько срочно и
            что это даст.
          </PlannedState>
          <p className="text-[12px] text-text-tertiary">
            План пуст. Добавьте пятно из досье — кнопка «В план обследования».
          </p>
        </div>
      )}
    </ShellSlot>
  );
}
