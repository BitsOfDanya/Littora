import type { ReactNode } from "react";
import type { LegendKind } from "@/config/layers";
import { DRIFT, type Ground, rampFor } from "@/features/map/ramps";
import { SeverityGlyph } from "@/ui/indicators";
import { coverageTicks, DivergingLegend, LegendRamp } from "./legend-ramp";
import {
  BeachingSwatch,
  ConfidenceSwatch,
  FootprintSwatch,
  HindcastSwatch,
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

export function LayerLegend({ kind, ground }: { kind: LegendKind; ground: Ground }) {
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
