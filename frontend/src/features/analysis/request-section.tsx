"use client";

import { useState } from "react";
import { useSceneCatalogState, useScenes } from "@/data/scenes";
import type { AreaOfInterest } from "@/domain/aoi";
import type { SceneSummary } from "@/domain/scene";
import type { Analysis } from "@/lib/api/analyses";
import { describeApiError } from "@/lib/api/errors";
import { formatPercent } from "@/lib/format/numbers";
import { formatUtcDateTime } from "@/lib/format/time";
import {
  type AnalysisAreaMode,
  useAnalysisStore,
  WINDOW_DAYS,
  type WindowDays,
} from "@/state/analysis-store";
import { useWorkspaceStore } from "@/state/workspace-store";
import { Button } from "@/ui/button";
import { cn } from "@/ui/cn";
import { KeyValue, KeyValueList } from "@/ui/key-value";
import { PanelSection } from "@/ui/section";
import { Segmented } from "@/ui/segmented";
import { formatDay } from "./format";
import { RunProgress } from "./run-progress";
import {
  useAnalysisRunStart,
  useCaseTargets,
  useRequestPlan,
  useRunAnalysis,
  useSavedMatch,
} from "./use-analysis";

const AREA_OPTIONS = [
  { value: "aoi", label: "весь участок" },
  { value: "view", label: "вид карты" },
] as const;

const WINDOW_OPTIONS = WINDOW_DAYS.map((days) => ({
  value: String(days) as `${WindowDays}`,
  label: `±${days}`,
  title: days === 0 ? "только день снимка" : `±${days} сут от даты снимка`,
}));

export const FIELD_CONTROL =
  "h-7 min-w-0 rounded-[var(--radius-ctl)] border border-line-control bg-surface-raised px-2 text-[13px] text-text-primary hover:border-line-strong";

function SceneLine({ scene }: { scene: SceneSummary }) {
  const coverage = scene.areaCoverage;
  return (
    <KeyValue
      label="Снимок"
      hint={`облачность тайла ${formatPercent(scene.cloudCover)}${coverage === undefined ? "" : ` · покрытие ${formatPercent(coverage)}`}`}
    >
      {scene.platform} · T{scene.mgrsTile} · {formatUtcDateTime(scene.acquiredAt)}
    </KeyValue>
  );
}

function CatalogLine() {
  const catalog = useSceneCatalogState();
  const text =
    catalog.status === "loading"
      ? "запрос каталога…"
      : catalog.status === "error"
        ? catalog.message
        : catalog.status === "ready"
          ? `нет снимков за ${formatDay(catalog.query.dateFrom)}–${formatDay(catalog.query.dateTo)}`
          : "каталог недоступен";
  return (
    <KeyValue label="Снимок" hint="будет выбран ближайший к дате">
      <span className="font-sans text-[12px] font-normal text-text-secondary">{text}</span>
    </KeyValue>
  );
}

function SurveyDates({ aoi }: { aoi: AreaOfInterest }) {
  const scenes = useScenes();
  const selectScene = useWorkspaceStore((state) => state.selectScene);
  const sceneId = useWorkspaceStore((state) => state.sceneId);
  const survey = aoi.survey;
  if (!survey) return null;
  const list = scenes.origin === "api" ? scenes.data : [];
  return (
    <KeyValue label={`Учёт с судна · ${survey.source}`} hint={survey.events.join(", ")}>
      <span className="flex flex-wrap justify-end gap-1">
        {survey.dates.map((day) => {
          const match = list
            .filter((scene) => scene.acquiredAt.startsWith(day))
            .sort((a, b) => (b.areaCoverage ?? 0) - (a.areaCoverage ?? 0))[0];
          const active = match !== undefined && match.id === sceneId;
          return (
            <button
              key={day}
              type="button"
              disabled={!match}
              title={match ? `Выбрать снимок ${match.id}` : "Снимка в этот день нет в каталоге"}
              onClick={() => match && selectScene(match.id)}
              className={cn(
                "h-6 rounded-[var(--radius-ctl)] border border-line-control px-1.5 font-mono text-[12px] hover:border-line-strong disabled:cursor-not-allowed disabled:border-dashed disabled:text-text-tertiary",
                active && "shadow-[inset_0_0_0_1px_var(--text-primary)]",
              )}
            >
              {formatDay(day)}
            </button>
          );
        })}
      </span>
    </KeyValue>
  );
}

function TargetPicker({ fallback }: { fallback: string | undefined }) {
  const targets = useCaseTargets().data;
  const targetKey = useAnalysisStore((state) => state.targetKey);
  const setTarget = useAnalysisStore((state) => state.setTarget);
  if (!targets) return null;
  const standard = fallback ?? targets.primary;
  return (
    <label className="flex flex-col gap-1 text-[12px] text-text-secondary">
      Целевая величина
      <select
        className={FIELD_CONTROL}
        value={targetKey ?? standard}
        onChange={(event) => setTarget(event.target.value === standard ? null : event.target.value)}
      >
        {targets.targets.map((target) => (
          <option key={target.key} value={target.key}>
            {target.title} · {target.events} событ.
          </option>
        ))}
      </select>
    </label>
  );
}

function isStale(analysis: Analysis, scene: SceneSummary | null, windowDays: number): boolean {
  if (scene && analysis.scene?.id !== scene.id) return true;
  return analysis.request.window_days !== windowDays;
}

export function RequestSection({ analysis }: { analysis: Analysis | null }) {
  const { aoi, scene, areaMode, windowDays, plan } = useRequestPlan();
  const setAreaMode = useAnalysisStore((state) => state.setAreaMode);
  const setWindowDays = useAnalysisStore((state) => state.setWindowDays);
  const setAnalysis = useAnalysisStore((state) => state.setAnalysis);
  const saved = useSavedMatch();
  const run = useRunAnalysis();
  const runStart = useAnalysisRunStart();
  const running = run.isPending || runStart !== null;
  const [problem, setProblem] = useState<string | null>(null);

  const onRun = () => {
    const planned = plan();
    if ("problem" in planned) {
      setProblem(planned.problem);
      return;
    }
    setProblem(null);
    run.mutate(planned.request);
  };

  const error = problem ?? (run.isError ? describeApiError(run.error) : null);
  const stale = analysis !== null && !running && isStale(analysis, scene, windowDays);

  return (
    <PanelSection index="01" title="Запрос">
      <KeyValueList>
        {scene ? <SceneLine scene={scene} /> : <CatalogLine />}
        {aoi ? <SurveyDates aoi={aoi} /> : null}
      </KeyValueList>
      <div className="grid grid-cols-[auto_minmax(0,1fr)] items-center gap-x-3 gap-y-2 pt-1 text-[12px] text-text-secondary">
        <span>Район</span>
        <Segmented<AnalysisAreaMode>
          label="Район анализа"
          value={areaMode}
          options={AREA_OPTIONS}
          onChange={setAreaMode}
          stretch
        />
        <span title="Поиск снимка и синхронность измерений">Окно, сут</span>
        <Segmented<`${WindowDays}`>
          label="Окно по времени, сутки"
          value={`${windowDays}`}
          options={WINDOW_OPTIONS}
          onChange={(value) => setWindowDays(Number(value) as WindowDays)}
          stretch
        />
      </div>
      <TargetPicker fallback={aoi?.survey?.target} />
      <div className="flex flex-col gap-1.5 pt-1">
        <Button
          variant="primary"
          size="lg"
          busy={running}
          disabled={running || !aoi}
          onClick={onRun}
        >
          {running ? "Читаем снимок и маску…" : "Запустить анализ"}
        </Button>
        <RunProgress startedAt={runStart} />
        {error ? <p className="text-[12px] leading-4 text-state-alarm">{error}</p> : null}
        {stale ? (
          <div className="flex flex-col items-start gap-1.5">
            <p className="text-[12px] leading-4 text-state-caution">
              Показан анализ за {formatDay(analysis.request.date)}: выбранный снимок или окно
              отличаются — запустите анализ заново.
            </p>
            {saved && saved.id !== analysis.id ? (
              <Button size="sm" onClick={() => setAnalysis(saved.id)}>
                Открыть сохранённый анализ за {formatDay(saved.request.date)}
              </Button>
            ) : null}
          </div>
        ) : null}
        <p className="text-[11px] leading-[14px] text-text-tertiary">
          Снимок, маска SCL и статус сохраняются на сервере; тот же запрос вернёт тот же результат.
        </p>
      </div>
    </PanelSection>
  );
}
