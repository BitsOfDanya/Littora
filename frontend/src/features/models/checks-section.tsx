import type { ReactNode } from "react";
import { DATA_LABELS } from "@/data/model-report";
import type {
  CollectionCheck,
  DetectionRate,
  DomainShiftCheck,
  ModelEvidence,
  NegativesCheck,
  PlpCheck,
  RegionCheck,
  ZoneFlagCheck,
} from "@/data/models";
import type { ClassificationMetrics } from "@/domain/model";
import { pluralRu } from "@/features/shell/orientation/plural";
import { formatSigned } from "@/lib/format/numbers";
import { cn } from "@/ui/cn";
import { Caps } from "@/ui/section";
import {
  DASH,
  formatCi95,
  formatCount,
  formatInterval,
  formatShare,
  formatValue,
  NARROW_NBSP,
} from "./format";
import { MetricBar } from "./metric-bar";
import { ReportSection } from "./report-section";

const HEAD = "pb-2 text-[12px] leading-4 font-medium text-text-secondary align-bottom";
const ROW = "border-b border-line-hairline";
const CELL = "py-2 align-middle text-[12px] leading-4 text-text-secondary";
const NUMBER = "font-mono text-[13px] leading-[18px] text-text-primary";
const NOTE = "mt-2 text-[12px] leading-4 text-text-tertiary";

function CheckHead({ title, detail }: { title: string; detail?: ReactNode }) {
  return (
    <div className="mb-3 flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
      <Caps>{title}</Caps>
      {detail ? <span className="text-[12px] text-text-secondary">{detail}</span> : null}
    </div>
  );
}

function Block({ children }: { children: ReactNode }) {
  return <figure className="col-span-12 m-0 min-w-0 @4xl:col-span-6">{children}</figure>;
}

function Share({ value }: { value: number }) {
  return <span className={NUMBER}>{formatShare(value)}</span>;
}

function MetricTriplet({ metrics }: { metrics: ClassificationMetrics }) {
  return (
    <>
      <td className={cn(CELL, "pl-3 text-right")}>
        <Share value={metrics.f1} />
      </td>
      <td className={cn(CELL, "pl-3 text-right")}>
        <Share value={metrics.precision} />
      </td>
      <td className={cn(CELL, "pl-3 text-right")}>
        <Share value={metrics.recall} />
      </td>
    </>
  );
}

function TripletHead({ first }: { first: string }) {
  return (
    <tr className="border-b border-text-primary">
      <th scope="col" className={cn(HEAD, "text-left")}>
        {first}
      </th>
      <th scope="col" className={cn(HEAD, "pl-3 text-right")}>
        F1
      </th>
      <th scope="col" className={cn(HEAD, "pl-3 text-right")}>
        P
      </th>
      <th scope="col" className={cn(HEAD, "pl-3 text-right")}>
        R
      </th>
    </tr>
  );
}

function DomainShiftBlock({ check }: { check: DomainShiftCheck }) {
  const [first, last] = [check.results[0], check.results.at(-1)];
  const drop = first && last && first !== last ? last.metrics.f1 - first.metrics.f1 : null;
  return (
    <Block>
      <CheckHead
        title="Сдвиг домена"
        detail={`${check.sourceName} · порог ${formatShare(check.threshold)} заморожен`}
      />
      <table className="w-full border-collapse">
        <caption className="sr-only">
          Одна модель и один порог на одних и тех же патчах test с разной обработкой снимков
        </caption>
        <thead>
          <TripletHead first="Обработка снимков test" />
        </thead>
        <tbody>
          {check.results.map((result) => (
            <tr key={result.code} className={ROW}>
              <th scope="row" className={cn(CELL, "text-left font-normal")}>
                <span className="text-text-primary">{DATA_LABELS[result.data] ?? result.data}</span>
                <span className="mt-0.5 block">
                  <MetricBar value={result.metrics.f1} interval={result.metricsCi95?.f1 ?? null} />
                </span>
              </th>
              <MetricTriplet metrics={result.metrics} />
            </tr>
          ))}
        </tbody>
      </table>
      <p className={NOTE}>
        Та же модель и тот же порог на тех же патчах test; меняется только обработка снимков.
        {drop !== null ? (
          <>
            {" "}
            Разница F1: <span className="font-mono">{formatSigned(drop, 3)}</span>.
          </>
        ) : null}
      </p>
    </Block>
  );
}

function RegionsBlock({ check }: { check: RegionCheck }) {
  return (
    <Block>
      <CheckHead title="Новая география" detail={check.name} />
      <table className="w-full border-collapse">
        <caption className="sr-only">
          Проверка с исключением региона: метрики на регионе, не видевшем обучения
        </caption>
        <thead>
          <TripletHead first="Регион · пикс. мусора" />
        </thead>
        <tbody>
          {check.regions.map((region) => (
            <tr key={region.region} className={ROW}>
              <th scope="row" className={cn(CELL, "text-left font-normal")}>
                <span className="text-text-primary">{region.region}</span>
                <span className="font-mono text-text-tertiary">
                  {" "}
                  · {formatCount(region.positives)}
                </span>
              </th>
              <MetricTriplet metrics={region.metrics} />
            </tr>
          ))}
          <tr className="border-b border-text-primary">
            <th scope="row" className={cn(CELL, "text-left font-semibold text-text-primary")}>
              Сводно
            </th>
            <MetricTriplet metrics={check.pooled} />
          </tr>
        </tbody>
      </table>
      {check.protocol ? <p className={NOTE}>Протокол: {check.protocol}.</p> : null}
    </Block>
  );
}

function NegativesBlock({ check }: { check: NegativesCheck }) {
  return (
    <Block>
      <CheckHead
        title="Чёрное море: заведомый фон"
        detail={`${formatCount(check.alarmPixels)} ${pluralRu(check.alarmPixels, ["срабатывание", "срабатывания", "срабатываний"])} на ${formatCount(check.pixels)}${NARROW_NBSP}пикс.`}
      />
      <table className="w-full border-collapse">
        <caption className="sr-only">
          Срабатывания сервисного детектора внутри полигонов, где мусора заведомо нет
        </caption>
        <thead>
          <tr className="border-b border-text-primary">
            <th scope="col" className={cn(HEAD, "text-left")}>
              Класс фона
            </th>
            <th scope="col" className={cn(HEAD, "pl-3 text-right")}>
              Полигонов
            </th>
            <th scope="col" className={cn(HEAD, "pl-3 text-right")}>
              Пикселей
            </th>
            <th scope="col" className={cn(HEAD, "pl-3 text-right")}>
              Срабатываний
            </th>
          </tr>
        </thead>
        <tbody>
          {check.classes.map((item) => (
            <tr key={item.label} className={ROW}>
              <th scope="row" className={cn(CELL, "text-left font-normal text-text-primary")}>
                {item.label}
              </th>
              <td className={cn(CELL, "pl-3 text-right font-mono")}>{item.polygons}</td>
              <td className={cn(CELL, "pl-3 text-right font-mono")}>{formatCount(item.pixels)}</td>
              <td
                className={cn(
                  CELL,
                  "pl-3 text-right font-mono",
                  item.alarmPixels > 0 && "font-semibold text-text-primary",
                )}
              >
                {formatCount(item.alarmPixels)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className={NOTE}>
        {check.polygons} {pluralRu(check.polygons, ["полигон", "полигона", "полигонов"])} разметки
        команды на {check.scenes} {pluralRu(check.scenes, ["сцене", "сценах", "сценах"])}; порог и
        постобработка на них не подбирались. Во всех окнах этих сцен сервис выделил{" "}
        {check.windowZones} {pluralRu(check.windowZones, ["зону", "зоны", "зон"])}; вне полигонов
        разметки нет, их верность не оценена.
      </p>
    </Block>
  );
}

const PLP_ROWS: readonly { key: "plastic" | "natural"; label: string }[] = [
  { key: "plastic", label: "Пластик и смесь" },
  { key: "natural", label: "Природные мишени" },
];

function RateRow({ label, rate, muted }: { label: string; rate: DetectionRate; muted?: boolean }) {
  return (
    <tr className={ROW}>
      <th
        scope="row"
        className={cn(
          CELL,
          "text-left font-normal",
          muted ? "text-text-secondary" : "text-text-primary",
        )}
      >
        {label}
      </th>
      <td className={cn(CELL, "pl-3 text-right font-mono")}>
        {rate.detected} из {rate.targets}
      </td>
      <td className={cn(CELL, "pl-3")} title={formatCi95(rate.ci95)}>
        <span className="flex items-center justify-end gap-2">
          <span className="w-9 text-right font-mono text-[13px] text-text-primary">
            {formatShare(rate.rate)}
          </span>
          <MetricBar value={rate.rate} interval={rate.ci95} />
        </span>
      </td>
      <td className={cn(CELL, "pl-3 text-right font-mono")}>{rate.zoneDetected ?? DASH}</td>
    </tr>
  );
}

function PlpBlock({ check }: { check: PlpCheck }) {
  return (
    <Block>
      <CheckHead
        title="Мишени Plastic Litter Project"
        detail="Лесбос, пластик известного размера"
      />
      <table className="w-full border-collapse">
        <caption className="sr-only">
          Доля мишеней, на которых вероятность детектора не ниже порога, с 95-процентными
          интервалами
        </caption>
        <thead>
          <tr className="border-b border-text-primary">
            <th scope="col" className={cn(HEAD, "text-left")}>
              Мишени
            </th>
            <th scope="col" className={cn(HEAD, "pl-3 text-right")}>
              Выше порога
            </th>
            <th scope="col" className={cn(HEAD, "pl-3 text-right")}>
              Доля · 95{NARROW_NBSP}% ДИ
            </th>
            <th scope="col" className={cn(HEAD, "pl-3 text-right")}>
              Зоной
            </th>
          </tr>
        </thead>
        <tbody>
          {PLP_ROWS.map(({ key, label }) => {
            const rate = check[key];
            return rate ? (
              <RateRow key={key} label={label} rate={rate} muted={key === "natural"} />
            ) : null;
          })}
          {check.bySize.map((rate) => (
            <RateRow key={rate.group} label={`пластик ${rate.group}`} rate={rate} muted />
          ))}
        </tbody>
      </table>
      <p className={NOTE}>
        Природные мишени — отрицательный контроль: срабатывание на них ложное.
        {check.threshold ? ` Порог — ${check.threshold}.` : null}
        {check.background ? (
          <>
            {" "}
            Фон: {check.background.zones}{" "}
            {pluralRu(check.background.zones, ["зона", "зоны", "зон"])} на{" "}
            {formatValue(check.background.waterKm2, 0)}
            {NARROW_NBSP}км² воды в {check.background.windows} окнах; в кольце вокруг мишеней
            срабатываний — {check.background.ringAlarmPixels}.
          </>
        ) : null}
      </p>
    </Block>
  );
}

function FlagBlock({ check }: { check: ZoneFlagCheck }) {
  return (
    <Block>
      <CheckHead
        title={`Флаг ${check.title}`}
        detail={check.inService ? "в сервисе, зону не скрывает" : "выключен"}
      />
      <table className="w-full border-collapse">
        <caption className="sr-only">Доля отмеченных объектов по группам и частям выборки</caption>
        <thead>
          <tr className="border-b border-text-primary">
            <th scope="col" className={cn(HEAD, "text-left")}>
              Выборка
            </th>
            <th scope="col" className={cn(HEAD, "pl-3 text-left")}>
              Группа
            </th>
            <th scope="col" className={cn(HEAD, "pl-3 text-right")}>
              Отмечено
            </th>
            <th scope="col" className={cn(HEAD, "pl-3 text-right")}>
              Доля
            </th>
          </tr>
        </thead>
        <tbody>
          {check.shares.map((row) => (
            <tr key={`${row.part}-${row.group}`} className={ROW}>
              <th scope="row" className={cn(CELL, "text-left font-normal")}>
                {row.part}
              </th>
              <td className={cn(CELL, "pl-3 text-text-primary")}>{row.group}</td>
              <td className={cn(CELL, "pl-3 text-right font-mono")}>
                {formatCount(row.flagged)} из {formatCount(row.objects)}
              </td>
              <td className={cn(CELL, "pl-3 text-right")}>
                <Share value={row.share ?? Number.NaN} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {check.discrimination.length ? (
        <ul className="mt-2 flex flex-col gap-0.5 text-[12px] leading-4 text-text-secondary">
          {check.discrimination.map((row) => (
            <li key={`${row.part}-${row.measure}`}>
              {row.part}: {row.measure} —{" "}
              <span className="font-mono text-text-primary">{formatShare(row.value)}</span>
              {row.ci95 ? `, ${formatCi95(row.ci95)}` : null}
            </li>
          ))}
        </ul>
      ) : null}
      <p className={NOTE}>Правило: {check.rule}.</p>
    </Block>
  );
}

function CollectionBlock({ check }: { check: CollectionCheck }) {
  return (
    <Block>
      <CheckHead title="Коллекция сервиса C1" detail="те же патчи в старой обработке L2A и в C1" />
      <table className="w-full border-collapse">
        <caption className="sr-only">
          F1 в режиме сервиса на одних и тех же патчах в двух обработках снимков
        </caption>
        <thead>
          <tr className="border-b border-text-primary">
            <th scope="col" className={cn(HEAD, "text-left")}>
              Выборка
            </th>
            <th scope="col" className={cn(HEAD, "pl-3 text-right")}>
              F1 C1
            </th>
            <th scope="col" className={cn(HEAD, "pl-3 text-right")}>
              F1 L2A
            </th>
            <th scope="col" className={cn(HEAD, "pl-3 text-right")}>
              C1 − L2A · 95{NARROW_NBSP}% ДИ
            </th>
          </tr>
        </thead>
        <tbody>
          {check.rows.map((row) => (
            <tr key={`${row.run}-${row.part}-${row.mode}`} className={ROW}>
              <th scope="row" className={cn(CELL, "text-left font-normal")}>
                <span className="text-text-primary">
                  {row.part}, {row.mode}
                </span>
                <span className="block text-[11px] text-text-tertiary">
                  {row.inService ? "в сервисе" : row.run} · {formatCount(row.patches)} патчей,{" "}
                  {row.scenes} {pluralRu(row.scenes, ["сцена", "сцены", "сцен"])}
                </span>
              </th>
              <td className={cn(CELL, "pl-3 text-right")} title={formatCi95(row.c1Ci95)}>
                <Share value={row.c1F1} />
              </td>
              <td className={cn(CELL, "pl-3 text-right")} title={formatCi95(row.l2aCi95)}>
                <Share value={row.l2aF1} />
              </td>
              <td className={cn(CELL, "pl-3 text-right font-mono")}>
                {formatSigned(row.difference, 3)}
                {row.differenceCi95 ? (
                  <span className="block text-[11px] text-text-tertiary">
                    {formatInterval(row.differenceCi95)}
                  </span>
                ) : null}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className={NOTE}>
        {check.alignment}. Сервис читает C1, а обучение и основные метрики — на старой обработке;
        здесь видно, переносятся ли они. Правило выбора модели: {check.rule}.
      </p>
    </Block>
  );
}

export function hasChecks(evidence: ModelEvidence): boolean {
  return Boolean(
    evidence.domainShift.length ||
    evidence.regions.length ||
    evidence.negatives ||
    evidence.plp ||
    evidence.zoneFlags.length,
  );
}

export function ChecksSection({ evidence, index }: { evidence: ModelEvidence; index: number }) {
  return (
    <ReportSection id="checks" index={index}>
      <div className="grid grid-cols-12 gap-x-8 gap-y-8">
        {evidence.domainShift.map((check) => (
          <DomainShiftBlock key={check.source} check={check} />
        ))}
        {evidence.regions.map((check) => (
          <RegionsBlock key={check.run} check={check} />
        ))}
        {evidence.negatives ? <NegativesBlock check={evidence.negatives} /> : null}
        {evidence.plp ? <PlpBlock check={evidence.plp} /> : null}
        {evidence.collection ? <CollectionBlock check={evidence.collection} /> : null}
        {evidence.zoneFlags.map((check) => (
          <FlagBlock key={check.kind} check={check} />
        ))}
      </div>
    </ReportSection>
  );
}
