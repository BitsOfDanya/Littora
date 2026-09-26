"use client";

import { findAoi } from "@/config/aois";
import { CopyButton } from "@/features/inspector/dossier/copy-button";
import { InspectorFrame } from "@/features/inspector/parts/inspector-frame";
import { Readout, ReadoutGrid } from "@/features/inspector/parts/readout-grid";
import { fitTo } from "@/features/map/camera";
import { useMainMap } from "@/features/map/use-main-map";
import type { Analysis } from "@/lib/api/analyses";
import { formatLngLat } from "@/lib/format/coordinates";
import { formatArea, formatNumber, formatPercent } from "@/lib/format/numbers";
import { formatUtcDateTime } from "@/lib/format/time";
import { useAnalysisStore } from "@/state/analysis-store";
import { useWorkspaceStore } from "@/state/workspace-store";
import { Button } from "@/ui/button";
import { KeyValue, KeyValueList } from "@/ui/key-value";
import { PanelSection } from "@/ui/section";
import { StatusTag } from "@/ui/status-tag";
import { QUALITY_CLASSES } from "./analysis-copy";
import { ConditionsRows } from "./conditions-rows";
import { formatDay } from "./format";
import { DriftAction, StaleNote } from "./result-sections";
import { ZoneReview } from "@/features/review/zone-review";
import { ZoneComparison } from "./zone-comparison";
import { ZoneCrop } from "./zone-crop";
import {
  coverageArea,
  coverageRange,
  formatProbability,
  type RealZone,
  type ZoneAdviceKind,
  zoneAdvice,
  zoneBounds,
  zoneColor,
} from "./zones";

const ZONE_FIT_MAX_ZOOM = 15;

const ADVICE_BORDERS: Readonly<Record<ZoneAdviceKind, string>> = {
  survey: "border-state-ok",
  recheck: "border-state-caution",
  not_debris: "border-line-strong",
};

function uncertaintyParts(zone: RealZone, threshold: number | null): string[] {
  const parts: string[] = [];
  if (zone.probabilityMax !== null)
    parts.push(
      `вероятность ${formatProbability(zone.probabilityMax)}${threshold === null ? "" : ` при пороге ${formatNumber(threshold, 2)}`}, калибр. на val`,
    );
  if (zone.stability)
    parts.push(`устойчивость ${formatPercent(zone.stability.agreement, 0)} из 8 видов`);
  if (zone.coverage) parts.push(`доля покрытия ${coverageRange(zone.coverage)}`);
  return parts;
}

function AdviceNote({ zone, threshold }: { zone: RealZone; threshold: number | null }) {
  const advice = zoneAdvice(zone);
  const parts = uncertaintyParts(zone, threshold);
  return (
    <div
      className={`flex flex-col gap-1 border-l-2 bg-surface-raised px-2.5 py-2 text-[12px] leading-4 ${ADVICE_BORDERS[advice.kind]}`}
    >
      <span className="font-semibold text-text-primary">Решение: {advice.title}</span>
      <span className="text-text-secondary">{advice.reason}</span>
      {parts.length ? (
        <span className="text-text-tertiary">Неопределённость: {parts.join(" · ")}</span>
      ) : null}
    </div>
  );
}

const CLASS_LABELS: Readonly<Record<string, string>> = Object.fromEntries(
  QUALITY_CLASSES.map((entry) => [entry.key, entry.label]),
);

function sclText(scl: RealZone["scl"]): string | null {
  if (!scl) return null;
  const parts = Object.entries(scl)
    .filter(([, share]) => share > 0)
    .sort(([, a], [, b]) => b - a)
    .map(([key, share]) => `${CLASS_LABELS[key] ?? key} ${formatPercent(share)}`);
  return parts.length ? parts.join(" · ") : null;
}

function ZoneHeader({
  analysis,
  zone,
  total,
}: {
  analysis: Analysis;
  zone: RealZone;
  total: number;
}) {
  const [red, green, blue] = zoneColor(zone.probabilityMax, analysis.detection.threshold ?? null);
  return (
    <div className="flex flex-col gap-1.5">
      <p className="flex items-center gap-2 font-mono text-[15px] leading-5 font-semibold text-text-primary">
        <span
          aria-hidden
          className="size-3 rounded-[1px] border border-line-hairline"
          style={{ background: `rgb(${red},${green},${blue})` }}
        />
        {zone.id}
        <span className="font-sans text-[12px] font-normal text-text-secondary">
          {zone.rank} из {total} по вероятности
        </span>
      </p>
      <span className="flex flex-wrap gap-1.5">
        <StatusTag tone="alarm">обнаружено моделью</StatusTag>
        <StatusTag tone="neutral">не проверено на месте</StatusTag>
      </span>
    </div>
  );
}

export function ZoneDossier({
  analysis,
  zone,
  total,
}: {
  analysis: Analysis;
  zone: RealZone;
  total: number;
}) {
  const map = useMainMap();
  const aoi = findAoi(useWorkspaceStore((state) => state.aoiId));
  const selectZone = useAnalysisStore((state) => state.selectZone);
  const { detection, scene } = analysis;
  const threshold = detection.threshold ?? null;
  const classes = sclText(zone.scl);
  const bounds = zoneBounds(zone);

  return (
    <InspectorFrame
      label={`Досье ${zone.id}`}
      eyebrow="Зона детектора · Sentinel-2 L2A"
      crumbs={[
        { label: aoi?.name ?? "Район", serif: true },
        { label: formatDay(analysis.request.date), onSelect: () => selectZone(null) },
        { label: zone.id },
      ]}
      onClose={() => selectZone(null)}
      selectionRule
      header={<ZoneHeader analysis={analysis} zone={zone} total={total} />}
      footer={
        <div className="flex w-full flex-wrap items-center gap-2">
          <Button
            onClick={() => {
              if (map && bounds) fitTo(map, bounds, { maxZoom: ZONE_FIT_MAX_ZOOM });
            }}
            disabled={!map || !bounds}
          >
            Показать на карте
          </Button>
          <Button variant="quiet" onClick={() => selectZone(null)}>
            К анализу района
          </Button>
        </div>
      }
    >
      <PanelSection index="01" title="Сводка">
        {analysis.stale ? <StaleNote analysis={analysis} /> : null}
        <AdviceNote zone={zone} threshold={threshold} />
        <ReadoutGrid>
          <Readout
            label="Вероятность, макс. (калибр.)"
            value={formatProbability(zone.probabilityMax)}
            interval={`средняя ${formatProbability(zone.probabilityMean)}`}
            note={
              threshold === null
                ? "оценка модели, калибровка на валидации"
                : `порог ${formatNumber(threshold, 3)}, калибровка на валидации`
            }
          />
          <Readout
            label="Площадь"
            value={zone.areaM2 === null ? "—" : formatArea(zone.areaM2)}
            interval={
              zone.pixels === null ? undefined : `пикселей 10 м: ${formatNumber(zone.pixels)}`
            }
            note="по пикселям выше порога"
          />
          {zone.coverage ? (
            <Readout
              label="Доля покрытия пикселя"
              value={formatPercent(zone.coverage.mean, 0)}
              interval={coverageRange(zone.coverage)}
              note={`${coverageArea(zone.coverage)}; оценка смешения с водой в NIR, «?» — граница не определена в мутной воде`}
            />
          ) : null}
        </ReadoutGrid>
        {zone.flags.length ? (
          <div className="flex flex-col gap-1 rounded-[2px] border border-line-hairline px-2.5 py-2 text-[12px] leading-4">
            <span className="text-[11px] font-semibold text-text-secondary">
              Есть признаки ложной зоны — она не скрыта, решать вам
            </span>
            {zone.flags.map((flag) => (
              <span key={flag.kind} className="text-text-primary">
                {flag.label}
                <span className="text-text-secondary"> · {flag.evidence.join("; ")}</span>
              </span>
            ))}
          </div>
        ) : null}
        <KeyValueList>
          {zone.centroid ? (
            <KeyValue label="Центр зоны">
              {formatLngLat(zone.centroid)}
              <CopyButton
                value={`${zone.centroid[1].toFixed(5)}, ${zone.centroid[0].toFixed(5)}`}
                label="Скопировать координаты"
              />
            </KeyValue>
          ) : null}
          <KeyValue label="Детектор">
            <span className="font-sans text-[12px] font-normal">{detection.model ?? "—"}</span>
          </KeyValue>
          {zone.stability ? (
            <KeyValue label="Устойчивость к поворотам">
              <span className="font-sans text-[12px] font-normal">
                {formatPercent(zone.stability.agreement, 0)} видов из {zone.stability.views}
              </span>
            </KeyValue>
          ) : null}
        </KeyValueList>
        <p className="text-[11px] leading-[14px] text-text-tertiary">
          Вероятность и площадь — оценка модели по снимку, не измерение; природа материала без
          проверки на месте не установлена.
        </p>
      </PanelSection>
      <PanelSection index="02" title="Сопоставление с измерениями с судна">
        <ZoneComparison analysis={analysis} zone={zone} />
      </PanelSection>
      <PanelSection index="03" title="Снимок">
        <ZoneCrop analysis={analysis} zone={zone} />
      </PanelSection>
      <PanelSection index="04" title="Условия съёмки">
        <KeyValueList>
          {scene ? (
            <>
              <KeyValue label="Время съёмки">{formatUtcDateTime(scene.acquired_at)}</KeyValue>
              <KeyValue label="Спутник · тайл">
                {scene.platform} · T{scene.tile}
              </KeyValue>
              <KeyValue label="Облачность тайла">
                {scene.cloud_cover === null ? "—" : formatPercent(scene.cloud_cover / 100)}
              </KeyValue>
              {scene.sun_elevation !== null ? (
                <KeyValue label="Высота Солнца">{formatNumber(scene.sun_elevation, 0)}°</KeyValue>
              ) : null}
            </>
          ) : null}
          <KeyValue label="Маска SCL в зоне" hint={classes ? undefined : "нет в этом результате"}>
            <span className="font-sans text-[12px] font-normal">{classes ?? "—"}</span>
          </KeyValue>
          <ConditionsRows analysis={analysis} />
        </KeyValueList>
      </PanelSection>
      <PanelSection index="05" title="Проверка командой">
        <ZoneReview analysisId={analysis.id} zoneId={zone.id} />
      </PanelSection>
      <PanelSection index="06" title="Дальше">
        <DriftAction analysis={analysis} />
      </PanelSection>
    </InspectorFrame>
  );
}
