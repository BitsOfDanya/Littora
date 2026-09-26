"use client";

import { CopyButton } from "@/features/inspector/dossier/copy-button";
import { easeToIfOutside } from "@/features/map/camera";
import { useMainMap } from "@/features/map/use-main-map";
import { Readout, ReadoutGrid } from "@/features/inspector/parts/readout-grid";
import { type Analysis, type AnalysisQuality, analysisRequestOf } from "@/lib/api/analyses";
import { describeApiError } from "@/lib/api/errors";
import { formatArea, formatNumber, formatPercent } from "@/lib/format/numbers";
import { formatUtcDateTime } from "@/lib/format/time";
import { useAnalysisStore } from "@/state/analysis-store";
import { Button } from "@/ui/button";
import { cn } from "@/ui/cn";
import { KeyValue, KeyValueList } from "@/ui/key-value";
import { PanelSection } from "@/ui/section";
import { StatusTag } from "@/ui/status-tag";
import {
  BRIGHT_WATER,
  CONCENTRATION_UNIT,
  profileLabel,
  QUALITY_CLASSES,
  STATUS_HINTS,
  STATUS_TONES,
} from "./analysis-copy";
import { ConditionsRows } from "./conditions-rows";
import { formatConcentration, formatDay } from "./format";
import { LayerChips, TargetComparison } from "./result-extras";
import { RunProgress } from "./run-progress";
import { useAnalysisRunStart, useRunAnalysis } from "./use-analysis";
import { useDriftLaunch } from "./use-drift-launch";
import { formatProbability, toRealZones, zoneColor } from "./zones";

export const STALE_NOTE = "результат посчитан прежней версией модели";

type RerunNoteProps = { analysis: Analysis; progress?: boolean };

function RerunNote({
  analysis,
  text,
  action,
  progress = true,
}: RerunNoteProps & { text: string; action: string }) {
  const run = useRunAnalysis();
  const runStart = useAnalysisRunStart();
  const running = run.isPending || runStart !== null;
  return (
    <div className="flex flex-col items-start gap-1.5 rounded-[var(--radius-ctl)] bg-state-caution-wash px-2.5 py-2">
      <p className="text-[12px] leading-4 text-state-caution">{text}</p>
      <Button
        size="sm"
        variant="primary"
        busy={running}
        disabled={running}
        onClick={() => run.mutate(analysisRequestOf(analysis))}
      >
        {running ? "Пересчитываем…" : action}
      </Button>
      {progress ? <RunProgress startedAt={runStart} /> : null}
      {run.isError ? (
        <p className="text-[12px] leading-4 text-state-alarm">{describeApiError(run.error)}</p>
      ) : null}
    </div>
  );
}

export function StaleNote({ analysis, progress }: RerunNoteProps) {
  return (
    <RerunNote
      analysis={analysis}
      progress={progress}
      text={`Не текущий: ${STALE_NOTE}. Статус и зоны могут отличаться от нынешнего детектора.`}
      action="Пересчитать"
    />
  );
}

export function RetryNote({ analysis, progress }: RerunNoteProps) {
  return (
    <RerunNote
      analysis={analysis}
      progress={progress}
      text="Снимок не прочитался из архива — это сбой чтения, а не свойство снимка. Повторный запрос прочитает каналы заново."
      action="Повторить"
    />
  );
}

export function DriftAction({ analysis }: { analysis: Analysis }) {
  const { available, launch } = useDriftLaunch();
  if (!available || !analysis.detection.zones.length) return null;
  return (
    <div className="flex flex-col items-start gap-1">
      <Button variant="primary" size="md" onClick={() => launch(analysis.id)}>
        Сценарий дрейфа
      </Button>
      <p className="text-[11px] leading-[14px] text-text-tertiary">
        Откроет «Прогноз» с этим анализом: куда зоны унесёт за 6–72 ч и откуда они пришли.
      </p>
    </div>
  );
}

export function PendingResult({ isLoading, error }: { isLoading: boolean; error: unknown }) {
  return (
    <PanelSection index="02" title="Результат">
      <p className="text-[12px] leading-4 text-text-secondary">
        {isLoading
          ? "Загружаем сохранённый анализ…"
          : error
            ? `Анализ не загружен: ${describeApiError(error)}`
            : "Анализ ещё не запускался. Результат придёт с одним из статусов: обнаружено, не обнаружено, недостаточно данных, исследовательская оценка, концентрация недоступна."}
      </p>
    </PanelSection>
  );
}

const TIMING_LABELS: readonly [string, string][] = [
  ["quality_and_image_s", "снимок и маска"],
  ["read_s", "11 каналов"],
  ["inference_s", "сеть"],
  ["stability_s", "проверка поворотов"],
  ["structures_s", "сооружения OSM"],
];

function timingHint(timings: Record<string, number>): string {
  const parts = TIMING_LABELS.filter(([key]) => timings[key] !== undefined).map(
    ([key, label]) => `${label} ${formatNumber(timings[key], 1)} с`,
  );
  if (timings.tiles) parts.push(`окон сети ${formatNumber(timings.tiles)}`);
  return parts.join(" · ");
}

function flaggedZones(analysis: Analysis): number {
  return analysis.detection.zones.filter((zone) =>
    (zone.flags ?? []).some((flag) => flag.kind === "vessel" || flag.kind === "structure"),
  ).length;
}

function PlainSummary({ analysis }: { analysis: Analysis }) {
  const { detection, concentration } = analysis;
  const day = analysis.scene ? formatDay(analysis.scene.acquired_at.slice(0, 10)) : null;
  const zones = detection.zones.length;
  const flagged = flaggedZones(analysis);
  let first: string;
  if (analysis.status.status === "detected")
    first = `На снимке ${day ?? ""} найдено мест, похожих на скопления плавающего мусора: ${zones}.${flagged ? ` ${flagged} из них похожи на суда или сооружения — проверьте их в карточке зоны.` : ""}`;
  else if (analysis.status.status === "not_detected")
    first = `Снимок ${day ?? ""} пригоден, скоплений плавающего мусора не найдено.`;
  else
    first = `Результата по снимку нет: ${detection.reason}. Попробуйте другую дату или окно поиска.`;
  const second =
    concentration.value !== null
      ? `Концентрация для района — около ${formatConcentration(concentration.value)} ${CONCENTRATION_UNIT}${concentration.lower !== null && concentration.upper !== null ? ` (от ${formatConcentration(concentration.lower)} до ${formatConcentration(concentration.upper)})` : ""}: это оценка по измерениям с судна, а не подсчёт по снимку.`
      : "Концентрацию для этого района и даты оценить нельзя: рядом нет полевых измерений нужного сезона — где они есть, показано на карте зелёным пунктиром.";
  return (
    <div className="flex flex-col gap-1 rounded-[2px] border border-line-hairline bg-surface-raised px-2.5 py-2 text-[12px] leading-4">
      <span className="text-[11px] font-semibold text-text-secondary">Коротко</span>
      <span className="text-text-primary">{first}</span>
      <span className="text-text-primary">{second}</span>
    </div>
  );
}

export function ResultSection({ analysis }: { analysis: Analysis }) {
  const { detection, concentration } = analysis;
  const coverage = concentration.coverage
    ? ` · покрытие на проверке ${Math.round(concentration.coverage * 100)} %`
    : "";
  const interval =
    concentration.lower !== null && concentration.upper !== null
      ? `интервал ${formatConcentration(concentration.lower)}–${formatConcentration(concentration.upper)}${coverage}`
      : undefined;
  return (
    <PanelSection
      index="02"
      title="Результат"
      aside={
        <StatusTag tone={STATUS_TONES[analysis.status.status]}>{analysis.status.label}</StatusTag>
      }
    >
      {analysis.stale ? (
        <StaleNote analysis={analysis} progress={false} />
      ) : analysis.retryable ? (
        <RetryNote analysis={analysis} progress={false} />
      ) : null}
      <PlainSummary analysis={analysis} />
      {analysis.layers.image ? <LayerChips analysis={analysis} /> : null}
      <p className="text-[12px] leading-4 text-text-secondary">
        {STATUS_HINTS[analysis.status.status]}
      </p>
      <ReadoutGrid>
        <Readout
          label="Концентрация"
          value={formatConcentration(concentration.value)}
          unit={CONCENTRATION_UNIT}
          interval={interval}
          note={
            concentration.profile
              ? `${concentration.label} · ${profileLabel(concentration.profile)}`
              : concentration.label
          }
          tone={concentration.value === null ? "secondary" : "primary"}
        />
        <Readout
          label="Зоны модели"
          value={formatNumber(detection.zones.length)}
          note={`детекция: ${detection.label}`}
          tone={detection.status === "insufficient_data" ? "secondary" : "primary"}
        />
      </ReadoutGrid>
      <TargetComparison analysis={analysis} />
      <details className="group text-[12px] leading-4">
        <summary className="cursor-pointer text-text-secondary select-none hover:text-text-primary">
          Подробности для специалиста
        </summary>
        <KeyValueList>
          <KeyValue label="Причина статуса">
            <span className="font-sans text-[12px] font-normal">{detection.reason}</span>
          </KeyValue>
          <KeyValue label="Концентрация">
            <span className="font-sans text-[12px] font-normal">{concentration.reason}</span>
          </KeyValue>
          <KeyValue label="Детектор">{detection.model ?? "не подключён"}</KeyValue>
          <KeyValue label="Модель C">
            {concentration.model ??
              (analysis.models?.concentration ? "не применена" : "не подключена")}
          </KeyValue>
          {detection.threshold !== null && detection.threshold !== undefined ? (
            <KeyValue label="Порог вероятности" hint="выбран на валидации">
              {formatNumber(detection.threshold, 3)}
            </KeyValue>
          ) : null}
          <KeyValue label="Цель">
            <span className="font-sans text-[12px] font-normal">
              {analysis.target.title}, {analysis.target.size_class}
            </span>
          </KeyValue>
          {analysis.timings?.total_s !== undefined ? (
            <KeyValue label="Время расчёта" hint={timingHint(analysis.timings)}>
              {formatNumber(analysis.timings.total_s, 0)} с
            </KeyValue>
          ) : null}
        </KeyValueList>
      </details>
      {detection.zones.length ? <ZoneList analysis={analysis} /> : null}
      <DriftAction analysis={analysis} />
      {analysis.messages.length ? (
        <ul className="flex flex-col gap-1 text-[12px] leading-4 text-state-caution">
          {analysis.messages.map((message) => (
            <li key={message}>{message}</li>
          ))}
        </ul>
      ) : null}
    </PanelSection>
  );
}

const LISTED_ZONES = 8;

function ZoneList({ analysis }: { analysis: Analysis }) {
  const map = useMainMap();
  const zoneId = useAnalysisStore((state) => state.zoneId);
  const selectZone = useAnalysisStore((state) => state.selectZone);
  const zones = toRealZones(analysis.detection.zones);
  const threshold = analysis.detection.threshold ?? null;
  return (
    <div className="flex flex-col gap-1">
      <p className="text-[12px] leading-4 text-text-secondary">
        Зоны детектора: {zones.length} · площадь и вероятность — оценка модели; щелчок — досье
      </p>
      <ul className="flex flex-col rounded-[var(--radius-ctl)] border border-line-hairline">
        {zones.slice(0, LISTED_ZONES).map((zone) => {
          const [red, green, blue] = zoneColor(zone.probabilityMax, threshold);
          return (
            <li
              key={zone.id}
              className={cn(
                "border-b border-line-hairline last:border-b-0",
                zone.id === zoneId && "shadow-[inset_3px_0_0_var(--accent-selection)]",
              )}
            >
              <button
                type="button"
                aria-pressed={zone.id === zoneId}
                className="grid w-full grid-cols-[auto_minmax(0,1fr)_auto_auto] items-center gap-x-3 px-2 py-1 text-left font-mono text-[12px] hover:bg-surface-raised"
                onClick={() => {
                  selectZone(zone.id);
                  if (map && zone.centroid) easeToIfOutside(map, [...zone.centroid]);
                }}
              >
                <span
                  aria-hidden
                  className="size-2.5 rounded-[1px] border border-line-hairline"
                  style={{ background: `rgb(${red},${green},${blue})` }}
                />
                <span className="text-text-primary">{zone.id}</span>
                <span className="text-text-secondary">
                  {zone.areaM2 === null ? "—" : formatArea(zone.areaM2)}
                </span>
                <span className="text-text-primary">
                  p {formatProbability(zone.probabilityMax)}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
      {zones.length > LISTED_ZONES ? (
        <p className="text-[11px] leading-[14px] text-text-tertiary">
          Ещё {zones.length - LISTED_ZONES} — во вкладке «Объекты» и на карте.
        </p>
      ) : null}
    </div>
  );
}

function QualityBar({ quality }: { quality: AnalysisQuality }) {
  return (
    <div className="flex flex-col gap-1.5">
      <div
        role="img"
        aria-label="Состав пикселей района по маске SCL"
        className="flex h-3 w-full overflow-hidden rounded-[var(--radius-ctl)] border border-line-hairline"
      >
        {QUALITY_CLASSES.map((entry) =>
          quality[entry.key] > 0 ? (
            <span
              key={entry.key}
              title={`${entry.label}: ${formatPercent(quality[entry.key], 1)}`}
              style={{ width: `${quality[entry.key] * 100}%`, background: entry.color }}
            />
          ) : null,
        )}
      </div>
      <ul className="flex flex-wrap gap-x-3 gap-y-1 text-[12px] leading-4 text-text-secondary">
        {QUALITY_CLASSES.map((entry) => (
          <li key={entry.key} className="inline-flex items-center gap-1.5">
            <span
              aria-hidden
              className="size-2.5 rounded-[1px] border border-line-hairline"
              style={{ background: entry.color }}
            />
            {entry.label}
            <span className="font-mono text-text-primary">
              {formatPercent(quality[entry.key], quality[entry.key] < 0.01 ? 1 : 0)}
            </span>
          </li>
        ))}
      </ul>
      {quality.bright_water !== null ? (
        <p className="inline-flex items-center gap-1.5 text-[12px] leading-4 text-text-secondary">
          <span
            aria-hidden
            className="size-2.5 rounded-[1px] border border-line-hairline"
            style={{ background: BRIGHT_WATER.color }}
          />
          {BRIGHT_WATER.label}:{" "}
          <span className="font-mono text-text-primary">
            {formatPercent(quality.bright_water, 1)}
          </span>{" "}
          воды
        </p>
      ) : null}
    </div>
  );
}

export function SceneQualitySection({ analysis }: { analysis: Analysis }) {
  const { scene, quality } = analysis;
  if (!scene)
    return (
      <PanelSection index="03" title="Снимок и качество">
        <p className="text-[12px] leading-4 text-text-secondary">{analysis.detection.reason}</p>
      </PanelSection>
    );
  return (
    <PanelSection
      index="03"
      title="Снимок и качество"
      aside={
        quality ? (
          <StatusTag tone={quality.usable ? "ok" : "caution"}>
            {quality.usable ? "пригоден" : "непригоден"}
          </StatusTag>
        ) : null
      }
    >
      <KeyValueList>
        <KeyValue label="ID сцены">
          <span className="font-mono text-[11px] leading-[14px] font-normal break-all">
            {scene.id}
          </span>
          <CopyButton value={scene.id} label="Скопировать ID сцены" />
        </KeyValue>
        <KeyValue label="Спутник · тайл · орбита">
          {scene.platform} · T{scene.tile}
          {scene.relative_orbit === null
            ? ""
            : ` · R${String(scene.relative_orbit).padStart(3, "0")}`}
        </KeyValue>
        <KeyValue label="Время съёмки">{formatUtcDateTime(scene.acquired_at)}</KeyValue>
        <KeyValue label="Облачность тайла">
          {scene.cloud_cover === null ? "—" : formatPercent(scene.cloud_cover / 100)}
        </KeyValue>
        {scene.sun_elevation !== null ? (
          <KeyValue label="Высота Солнца">{formatNumber(scene.sun_elevation, 0)}°</KeyValue>
        ) : null}
        <ConditionsRows analysis={analysis} />
      </KeyValueList>
      {quality ? (
        <>
          <QualityBar quality={quality} />
          {quality.reasons.length ? (
            <p className="text-[12px] leading-4 text-state-caution">
              Непригоден: {quality.reasons.join(", ")}
            </p>
          ) : (
            <p className="text-[12px] leading-4 text-text-secondary">
              Облака, тени и пропуски в пределах порогов — снимок можно передавать детектору.
            </p>
          )}
        </>
      ) : null}
    </PanelSection>
  );
}
