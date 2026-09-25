import type { ConfuserLikelihood, ConfuserRow } from "@/data/monitor-dossier";
import { cn } from "@/ui/cn";
import { DemoTag } from "@/ui/demo-mark";
import { PanelSection } from "@/ui/section";

const WORD: Record<ConfuserLikelihood, string> = {
  excluded: "исключено",
  unlikely: "маловероятно",
  possible: "возможно",
  unchecked: "не проверено",
};

const FILLED: Record<ConfuserLikelihood, number> = {
  excluded: 0,
  unlikely: 1,
  possible: 2,
  unchecked: 0,
};

function LikelihoodBar({ likelihood }: { likelihood: ConfuserLikelihood }) {
  const filled = FILLED[likelihood];
  return (
    <span aria-hidden className="inline-flex gap-px">
      {[0, 1, 2, 3].map((step) => (
        <span
          key={step}
          className={cn(
            "block h-1.5 w-2.5 border",
            likelihood === "unchecked"
              ? "border-dashed border-text-tertiary"
              : step < filled
                ? "border-text-primary bg-text-primary"
                : "border-line-control",
          )}
        />
      ))}
    </span>
  );
}

export function ConfuserList({ rows, isDemo }: { rows: readonly ConfuserRow[]; isDemo: boolean }) {
  return (
    <PanelSection
      id="dossier-doubts"
      index="05"
      title="Почему это может быть не мусор"
      aside={isDemo ? <DemoTag /> : null}
      className="scroll-mt-[var(--inspector-pin,40px)]"
    >
      <ul className="flex flex-col">
        {rows.map((row) => (
          <li
            key={row.key}
            className="grid grid-cols-[minmax(0,1fr)_auto_auto] items-center gap-x-3 gap-y-0.5 border-b border-line-hairline py-1.5 last:border-b-0"
          >
            <span className="text-[13px] leading-[18px] text-text-primary">{row.label}</span>
            <span
              className={cn(
                "text-[12px] leading-4",
                row.likelihood === "possible"
                  ? "font-medium text-text-primary"
                  : "text-text-secondary",
              )}
            >
              {WORD[row.likelihood]}
            </span>
            <LikelihoodBar likelihood={row.likelihood} />
            <span className="col-span-3 text-[12px] leading-4 text-text-tertiary">
              {row.reason}
            </span>
          </li>
        ))}
      </ul>
    </PanelSection>
  );
}
