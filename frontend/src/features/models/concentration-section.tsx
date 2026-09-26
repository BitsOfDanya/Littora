import type {
  ConcentrationEstimate,
  ConcentrationProfile,
  SatelliteLinkCheck,
  ServedConcentration,
} from "@/data/models";
import { pluralRu } from "@/features/shell/orientation/plural";
import { cn } from "@/ui/cn";
import { DASH, formatDifference, formatShare, formatValue, NARROW_NBSP } from "./format";
import { ReportSection } from "./report-section";

const HEAD = "pb-2 text-[12px] leading-4 font-medium text-text-secondary align-bottom";
const CELL = "py-2.5 align-top text-[12px] leading-4 text-text-secondary @max-4xl:py-0";
const NUMBER = "block font-mono text-[13px] leading-[18px] text-text-primary";
const MINOR = "block font-mono text-[11px] leading-4 text-text-tertiary";
const NARROW_LABEL = "text-[11px] leading-[14px] text-text-tertiary @4xl:hidden";
const ROW =
  "border-b border-line-hairline @max-4xl:grid @max-4xl:grid-cols-2 @max-4xl:gap-x-4 @max-4xl:gap-y-2.5 @max-4xl:py-3 @2xl:@max-4xl:grid-cols-4";

const HEADS = [
  "Профиль",
  "Событий · дней",
  "MAE медианы",
  "MAE вложенного выбора",
  "Разница MAE, 95 % ДИ",
  "В сервисе",
] as const;

function ErrorCell({
  label,
  mae,
  rmse,
}: {
  label: string;
  mae: number | null;
  rmse: number | null;
}) {
  return (
    <td className={cn(CELL, "@4xl:pl-4 @4xl:text-right")}>
      <span className={NARROW_LABEL}>{label}</span>
      <span className={NUMBER}>{formatValue(mae)}</span>
      <span className={MINOR}>RMSE {formatValue(rmse)}</span>
    </td>
  );
}

function DifferenceCell({
  primary,
  shortlist,
}: {
  primary: ConcentrationEstimate | null;
  shortlist: ConcentrationEstimate | null;
}) {
  const difference = primary?.difference ?? null;
  return (
    <td className={cn(CELL, "@4xl:pl-4 @4xl:text-right")}>
      <span className={NARROW_LABEL}>{HEADS[4]}</span>
      <span className={NUMBER}>
        {difference ? formatDifference(difference.mean, difference.ci) : DASH}
      </span>
      <span className="block text-[11px] leading-4 text-text-secondary">
        {primary ? (primary.gain ? "выигрыш значим" : "выигрыш не значим") : DASH}
      </span>
      {shortlist?.difference ? (
        <span
          className={MINOR}
          title="Короткий список вариантов после разведочных прогонов на тех же данных — оценка оптимистична"
        >
          шорт-лист {formatDifference(shortlist.difference.mean, shortlist.difference.ci)}
        </span>
      ) : null}
    </td>
  );
}

function ServedCell({ served }: { served: ServedConcentration | null }) {
  if (!served)
    return (
      <td className={cn(CELL, "@4xl:pl-4")}>
        <span className={NARROW_LABEL}>{HEADS[5]}</span>
        <span className={NUMBER}>{DASH}</span>
      </td>
    );
  const model = served.model === "median" ? "медиана" : served.model;
  return (
    <td className={cn(CELL, "@4xl:pl-4")} title={served.reason ?? undefined}>
      <span className={NARROW_LABEL}>{HEADS[5]}</span>
      <span className="block text-[13px] leading-[18px] text-text-primary">
        {model}
        {served.value !== null ? (
          <>
            {" "}
            <span className="font-mono">{formatValue(served.value)}</span>
            {NARROW_NBSP}
            {served.unit}
          </>
        ) : null}
      </span>
      {served.coverageNominal !== null ? (
        <span className="block text-[11px] leading-4 text-text-tertiary">
          интервал {formatValue(served.coverageNominal * 100, 0)}
          {NARROW_NBSP}%, покрытие{" "}
          <span className="font-mono">{formatShare(served.coverageEmpirical)}</span>
        </span>
      ) : null}
    </td>
  );
}

function ProfileRow({ profile }: { profile: ConcentrationProfile }) {
  const primary = profile.primary;
  return (
    <tr className={ROW}>
      <th scope="row" className={cn(CELL, "text-left font-normal @max-4xl:col-span-full")}>
        <span className="block text-[13px] leading-[18px] font-medium text-text-primary">
          {profile.label}
        </span>
        <span className="block font-mono text-[11px] leading-4 break-all text-text-tertiary">
          {profile.profile}
        </span>
      </th>
      <td className={cn(CELL, "@4xl:pl-4 @4xl:text-right")}>
        <span className={NARROW_LABEL}>{HEADS[1]}</span>
        <span className={NUMBER}>
          {profile.events ?? DASH} · {profile.surveyDays ?? DASH}
        </span>
      </td>
      <ErrorCell
        label={HEADS[2]}
        mae={primary?.baselineMae ?? null}
        rmse={primary?.baselineRmse ?? null}
      />
      <ErrorCell
        label={HEADS[3]}
        mae={primary?.nestedMae ?? null}
        rmse={primary?.nestedRmse ?? null}
      />
      <DifferenceCell primary={primary} shortlist={profile.shortlist} />
      <ServedCell served={profile.served} />
    </tr>
  );
}

function LinkNote({ link }: { link: SatelliteLinkCheck }) {
  const significant = link.minPValue !== null && link.minPValue < 0.05;
  return (
    <p className="mt-2 text-[12px] leading-4 text-text-tertiary">
      Связь «снимок → концентрация»: {link.events} {pluralRu(link.events, ["пара", "пары", "пар"])}{" "}
      снимок — измерение того же дня, {link.correlations}{" "}
      {pluralRu(link.correlations, ["корреляция", "корреляции", "корреляций"])} Спирмена; наименьшее
      p = <span className="font-mono">{formatValue(link.minPValue, 2)}</span>
      {significant ? "." : " — значимой связи нет, поэтому концентрация по снимку не выводится."}
    </p>
  );
}

export function ConcentrationSection({
  profiles,
  link,
  index,
}: {
  profiles: readonly ConcentrationProfile[];
  link: SatelliteLinkCheck | null;
  index: number;
}) {
  return (
    <ReportSection id="concentration" index={index}>
      <table className="w-full border-collapse @max-4xl:block">
        <caption className="sr-only">
          Ошибка оценки концентрации по профилям: медиана профиля против вложенного выбора модели,
          разница с 95-процентным интервалом и модель, выданная в сервис
        </caption>
        <thead className="@max-4xl:sr-only">
          <tr className="border-b border-text-primary">
            {HEADS.map((head, column) => (
              <th
                key={head}
                scope="col"
                className={cn(
                  HEAD,
                  column === 0 ? "text-left" : column === 5 ? "pl-4 text-left" : "pl-4 text-right",
                )}
              >
                {head}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="@max-4xl:block @max-4xl:border-t @max-4xl:border-text-primary">
          {profiles.map((profile) => (
            <ProfileRow key={profile.profile} profile={profile} />
          ))}
        </tbody>
      </table>
      <p className="mt-3 text-[12px] leading-4 text-text-tertiary">
        MAE и RMSE в единицах профиля, среднее по повторам кросс-валидации; группы — дни съёмки.
        Разница — вложенный выбор минус медиана, кластерный бутстрэп по дням. Шорт-лист составлен
        после разведки на тех же данных, его оценка оптимистична.
      </p>
      {link ? <LinkNote link={link} /> : null}
    </ReportSection>
  );
}
