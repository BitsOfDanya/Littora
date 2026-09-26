import type { ReactNode } from "react";
import type { LegendKind } from "@/config/layers";
import { BRIGHT_WATER, QUALITY_CLASSES } from "@/features/analysis/analysis-copy";
import { ZONE_RAMP_CSS } from "@/features/analysis/zones";
import { GROUND_INK } from "@/features/map/palette";
import { BEACHING, DRIFT, type Ground, rampFor } from "@/features/map/ramps";
import { SeverityGlyph } from "@/ui/indicators";
import { DENSITY_CLASSES } from "@/features/analysis/density";
import { coverageTicks, DivergingLegend, LegendRamp } from "./legend-ramp";
import type { LayerTruth } from "./use-layer-truth";
import {
  AreaStatusSwatch,
  BeachingSwatch,
  ConfidenceSwatch,
  FootprintSwatch,
  HindcastSwatch,
  MaskClassSwatch,
  MeasurementSwatch,
  MedianSwatch,
  NestedEnvelopesSwatch,
  NoDataSwatch,
  ParticlesSwatch,
  RouteSwatch,
  SearchRadiusSwatch,
  TargetSwatch,
  UncertaintySwatch,
} from "./legend-swatches";

export function LegendNote({
  children,
  tone = "unit",
}: {
  children: ReactNode;
  tone?: "unit" | "source";
}) {
  return (
    <p
      className={
        tone === "unit"
          ? "text-[12px] leading-4 text-text-secondary"
          : "text-[12px] leading-4 text-text-tertiary"
      }
    >
      {children}
    </p>
  );
}

function LegendItems({ children }: { children: ReactNode }) {
  return <div className="flex flex-wrap items-center gap-x-3 gap-y-1">{children}</div>;
}

function LegendItem({ swatch, children }: { swatch: ReactNode; children: ReactNode }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-[12px] leading-4 text-text-secondary">
      {swatch}
      {children}
    </span>
  );
}

const HORIZON_ALPHAS: readonly number[] = Object.values(DRIFT.envelopeFillAlpha);

function EnvelopesLegend({ ground }: { ground: Ground }) {
  return (
    <>
      <LegendItems>
        <LegendItem swatch={<NestedEnvelopesSwatch ground={ground} alphas={HORIZON_ALPHAS} />}>
          {"+6…+72\u202Fч: дальше — бледнее"}
        </LegendItem>
      </LegendItems>
      <LegendNote>пунктир — прогноз, сплошная — наблюдение</LegendNote>
    </>
  );
}

function BeachingLegend({ ground }: { ground: Ground }) {
  return (
    <LegendItems>
      <LegendItem swatch={<BeachingSwatch ground={ground} severity="alarm" />}>
        <SeverityGlyph severity="alarm" size={12} />
        П1 · тревога
      </LegendItem>
      <LegendItem swatch={<BeachingSwatch ground={ground} severity="caution" />}>
        <SeverityGlyph severity="caution" size={12} />
        П2 · внимание
      </LegendItem>
    </LegendItems>
  );
}

export function hasLegend(kind: LegendKind): boolean {
  return !["composite", "hotspot-cells", "aoi-line", "graticule", "labels"].includes(kind);
}

function QualityMaskLegend({ ground }: { ground: Ground }) {
  return (
    <>
      <LegendItems>
        {QUALITY_CLASSES.filter((entry) => entry.key !== "water").map((entry) => (
          <LegendItem
            key={entry.key}
            swatch={<MaskClassSwatch ground={ground} color={entry.color} />}
          >
            {entry.label}
          </LegendItem>
        ))}
        <LegendItem swatch={<MaskClassSwatch ground={ground} color={BRIGHT_WATER.color} />}>
          яркая вода
        </LegendItem>
      </LegendItems>
      <LegendNote>маска SCL снимка; вода прозрачна · не наблюдалось — не «чистая вода»</LegendNote>
    </>
  );
}

function AnalysisAreaLegend({ ground }: { ground: Ground }) {
  const ink = BEACHING.ink[ground];
  return (
    <>
      <LegendItems>
        <LegendItem swatch={<AreaStatusSwatch ground={ground} color={ink.alarm} />}>
          обнаружено
        </LegendItem>
        <LegendItem
          swatch={<AreaStatusSwatch ground={ground} color={GROUND_INK[ground].outline} />}
        >
          не обнаружено
        </LegendItem>
        <LegendItem swatch={<AreaStatusSwatch ground={ground} color={ink.caution} />}>
          недостаточно данных
        </LegendItem>
      </LegendItems>
      <LegendNote>пунктир — район запроса; концентрация — в шт./км² в панели анализа</LegendNote>
    </>
  );
}

function ProbabilityLegend() {
  return (
    <>
      <div
        aria-hidden
        className="h-2.5 w-full rounded-[1px] border border-line-hairline"
        style={{
          background:
            "linear-gradient(90deg, rgba(255,236,179,0.1), rgba(255,214,102,0.5), rgba(255,160,60,0.75), rgba(235,90,50,0.9), rgba(200,30,60,1))",
        }}
      />
      <div className="flex justify-between font-mono text-[11px] text-text-tertiary">
        <span>¼ порога</span>
        <span>порог</span>
        <span>выше</span>
      </div>
      <LegendNote>вероятность детектора по пикселю 10 м; ниже ¼ порога не показано</LegendNote>
    </>
  );
}

function ZonesLegend() {
  return (
    <>
      <div
        aria-hidden
        className="h-2.5 w-full rounded-[1px] border border-line-hairline"
        style={{ background: ZONE_RAMP_CSS }}
      />
      <div className="flex justify-between font-mono text-[11px] text-text-tertiary">
        <span>порог</span>
        <span>p макс. зоны</span>
        <span>1</span>
      </div>
      <div className="flex flex-col gap-1 text-[11px] leading-[14px] text-text-secondary">
        <span className="flex items-center gap-2">
          <span
            aria-hidden
            className="size-2.5 rounded-full border border-state-alarm bg-state-alarm/60"
          />
          закрашенный маркер — проверить на месте
        </span>
        <span className="flex items-center gap-2">
          <span
            aria-hidden
            className="size-2.5 rounded-full border border-state-alarm bg-state-alarm/10"
          />
          бледный — перепроверить на следующем снимке
        </span>
        <span className="flex items-center gap-2">
          <span aria-hidden className="size-2.5 rounded-full border border-line-strong" />
          полый серый — похоже на судно или сооружение
        </span>
      </div>
      <LegendNote>
        связные пиксели выше порога; подпись — зона и p макс. · оценка модели, не измерение
      </LegendNote>
    </>
  );
}

function MeasurementsLegend({ ground }: { ground: Ground }) {
  return (
    <>
      <LegendItems>
        <LegendItem swatch={<MeasurementSwatch ground={ground} />}>измерение</LegendItem>
        <LegendItem swatch={<MeasurementSwatch ground={ground} hollow />}>0 шт./км²</LegendItem>
        <LegendItem swatch={<MeasurementSwatch ground={ground} faded />}>
          вне окна снимка
        </LegendItem>
      </LegendItems>
      <LegendNote>
        подпись — шт./км²; размер растёт с lg значения · натурные данные, не модель
      </LegendNote>
    </>
  );
}

export function LayerLegend({
  kind,
  ground,
  truth = "real",
}: {
  kind: LegendKind;
  ground: Ground;
  truth?: LayerTruth;
}) {
  switch (kind) {
    case "coverage-ramp": {
      const ramp = rampFor("coverage", ground);
      return (
        <>
          <LegendRamp ramp={ramp} ticks={coverageTicks(ramp)} label="Доля покрытия пикселя, %" />
          <LegendNote>{"% площади пикселя 10\u202Fм · ниже 1\u202F% не показано"}</LegendNote>
        </>
      );
    }
    case "confidence-lines":
      return (
        <>
          <LegendItems>
            <LegendItem swatch={<ConfidenceSwatch level="high" ground={ground} />}>
              высокая
            </LegendItem>
            <LegendItem swatch={<ConfidenceSwatch level="medium" ground={ground} />}>
              средняя
            </LegendItem>
            <LegendItem swatch={<ConfidenceSwatch level="low" ground={ground} />}>
              низкая
            </LegendItem>
          </LegendItems>
          <LegendNote>
            Подпись <span className="font-mono">LT-004 12₄</span> = покрытие {"12,4\u202F%"}
          </LegendNote>
        </>
      );
    case "uncertainty-hatch":
      return (
        <LegendItems>
          <LegendItem
            swatch={
              <>
                <UncertaintySwatch dense={false} ground={ground} />
                <UncertaintySwatch dense ground={ground} />
              </>
            }
          >
            штриховка гуще — модель менее уверена
          </LegendItem>
        </LegendItems>
      );
    case "nodata-hatch":
      if (truth === "real") return <QualityMaskLegend ground={ground} />;
      return (
        <LegendItems>
          <LegendItem swatch={<NoDataSwatch ground={ground} />}>
            не наблюдалось — это не «чистая вода»
          </LegendItem>
        </LegendItems>
      );
    case "footprint-line":
      return (
        <LegendItems>
          <LegendItem swatch={<FootprintSwatch ground={ground} />}>
            граница кадра Sentinel-2
          </LegendItem>
        </LegendItems>
      );
    case "analysis-area":
      return <AnalysisAreaLegend ground={ground} />;
    case "observation-marks":
      return <MeasurementsLegend ground={ground} />;
    case "density-classes":
      return (
        <div className="flex flex-col gap-1 text-[11px] leading-[14px] text-text-secondary">
          {DENSITY_CLASSES.map((entry, index) => (
            <span key={entry.label} className="flex items-center gap-2">
              <span
                aria-hidden
                className="h-2.5 w-4 rounded-[1px]"
                style={{
                  background: `rgba(${entry.color.slice(0, 3).join(",")},${entry.color[3] / 255})`,
                }}
              />
              {entry.label} ·{" "}
              {index === 0
                ? `до ${entry.max}`
                : entry.max === Infinity
                  ? `от ${DENSITY_CLASSES[index - 1].max}`
                  : `${DENSITY_CLASSES[index - 1].max}–${entry.max}`}{" "}
              м²/км²
            </span>
          ))}
          <span>ячейка 1 км; сумма площади материала зон без «похоже на судно»</span>
        </div>
      );
    case "concentration-domains":
      return (
        <div className="flex flex-col gap-1 text-[11px] leading-[14px] text-text-secondary">
          <span className="flex items-center gap-2">
            <span
              aria-hidden
              className="h-2.5 w-4 border border-dotted border-state-ok bg-state-ok/10"
            />
            до 60 км от точек полевого профиля и в его сезон ±30 сут
          </span>
          <span>вне области — «концентрация недоступна»</span>
        </div>
      );
    case "team-labels":
      return (
        <div className="flex flex-col gap-1 text-[11px] leading-[14px] text-text-secondary">
          <span className="flex items-center gap-2">
            <span aria-hidden className="h-2.5 w-4 border border-dashed border-text-secondary" />
            заведомый фон: суда, садки, шлейфы, облака, вода
          </span>
          <span className="flex items-center gap-2">
            <span aria-hidden className="size-2 rounded-full bg-text-secondary" />
            аудит зон детектора: что это на самом деле
          </span>
        </div>
      );
    case "probability-ramp":
      return <ProbabilityLegend />;
    case "zone-outline":
      return <ZonesLegend />;
    case "delta-ramp":
      return (
        <>
          <DivergingLegend
            ramp={rampFor("change", ground)}
            limit={10}
            unit="п. п."
            label="Изменение покрытия A → B"
          />
          <LegendNote>синий — убыль, жёлтый — рост</LegendNote>
        </>
      );
    case "envelopes":
      return <EnvelopesLegend ground={ground} />;
    case "median-path":
      return (
        <LegendItems>
          <LegendItem swatch={<MedianSwatch ground={ground} />}>
            {"кольца — горизонты +6…+72\u202Fч"}
          </LegendItem>
        </LegendItems>
      );
    case "hindcast-path":
      return (
        <LegendItems>
          <LegendItem swatch={<HindcastSwatch ground={ground} />}>
            {"−48\u202Fч · откуда пришло"}
          </LegendItem>
        </LegendItems>
      );
    case "particles":
      return (
        <LegendItems>
          <LegendItem swatch={<ParticlesSwatch ground={ground} />}>
            направление поверхностного течения
          </LegendItem>
        </LegendItems>
      );
    case "beaching":
      return <BeachingLegend ground={ground} />;
    case "target-rings":
      return (
        <LegendItems>
          <LegendItem swatch={<TargetSwatch ground={ground} />}>
            номер — очередь по сводному баллу
          </LegendItem>
        </LegendItems>
      );
    case "route-line":
      return (
        <LegendItems>
          <LegendItem swatch={<RouteSwatch ground={ground} />}>от порта, в обход суши</LegendItem>
        </LegendItems>
      );
    case "search-radius":
      return (
        <LegendItems>
          <LegendItem swatch={<SearchRadiusSwatch ground={ground} />}>
            с учётом дрейфа к выходу
          </LegendItem>
        </LegendItems>
      );
    default:
      return null;
  }
}
