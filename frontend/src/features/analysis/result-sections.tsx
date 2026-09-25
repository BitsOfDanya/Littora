"use client";

import { CopyButton } from "@/features/inspector/dossier/copy-button";
import { Readout, ReadoutGrid } from "@/features/inspector/parts/readout-grid";
import type { Analysis, AnalysisQuality } from "@/lib/api/analyses";
import { describeApiError } from "@/lib/api/errors";
import { formatNumber, formatPercent } from "@/lib/format/numbers";
import { formatUtcDateTime } from "@/lib/format/time";
import { KeyValue, KeyValueList } from "@/ui/key-value";
import { PanelSection } from "@/ui/section";
import { StatusTag } from "@/ui/status-tag";
import {
  BRIGHT_WATER,
  CONCENTRATION_UNIT,
  QUALITY_CLASSES,
  STATUS_HINTS,
  STATUS_TONES,
} from "./analysis-copy";
import { formatConcentration } from "./format";

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

export function ResultSection({ analysis }: { analysis: Analysis }) {
  const { detection, concentration } = analysis;
  const interval =
    concentration.lower !== null && concentration.upper !== null
      ? `интервал ${formatConcentration(concentration.lower)}–${formatConcentration(concentration.upper)}`
      : undefined;
  return (
    <PanelSection
      index="02"
      title="Результат"
      aside={
        <StatusTag tone={STATUS_TONES[analysis.status.status]}>{analysis.status.label}</StatusTag>
      }
    >
      <p className="text-[12px] leading-4 text-text-secondary">
        {STATUS_HINTS[analysis.status.status]}
      </p>
      <ReadoutGrid>
        <Readout
          label="Концентрация по снимку"
          value={formatConcentration(concentration.value)}
          unit={CONCENTRATION_UNIT}
          interval={interval}
          note={concentration.label}
          tone={concentration.value === null ? "secondary" : "primary"}
        />
        <Readout
          label="Зоны модели"
          value={formatNumber(detection.zones.length)}
          note={`детекция: ${detection.label}`}
          tone={detection.status === "insufficient_data" ? "secondary" : "primary"}
        />
      </ReadoutGrid>
      <KeyValueList>
        <KeyValue label="Причина статуса">
          <span className="font-sans text-[12px] font-normal">{detection.reason}</span>
        </KeyValue>
        <KeyValue label="Концентрация">
          <span className="font-sans text-[12px] font-normal">{concentration.reason}</span>
        </KeyValue>
        <KeyValue label="Детектор · модель C">
          {detection.model ?? "не подключён"} · {concentration.model ?? "не подключена"}
        </KeyValue>
        <KeyValue label="Цель">
          <span className="font-sans text-[12px] font-normal">
            {analysis.target.title}, {analysis.target.size_class}
          </span>
        </KeyValue>
      </KeyValueList>
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
