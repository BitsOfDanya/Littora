import type { CSSProperties } from "react";
import type { ModelEvaluation } from "@/data/models";
import { cn } from "@/ui/cn";
import { MATRIX_COPY } from "./copy";
import { rowNormalise, inkOpacity, prefersInverseText } from "./confusion";
import { DASH, formatShare } from "./format";
import styles from "./report.module.css";

function cellStyle(share: number): CSSProperties {
  const opacity = inkOpacity(share);
  return {
    backgroundColor: `color-mix(in srgb, var(--text-primary) ${(opacity * 100).toFixed(1)}%, transparent)`,
    color: prefersInverseText(share) ? "var(--surface-panel)" : "var(--text-primary)",
  };
}

type ConfusionMatrixProps = {
  model: ModelEvaluation | null;
  classes: readonly string[];
};

export function ConfusionMatrix({ model, classes }: ConfusionMatrixProps) {
  const shares = model ? rowNormalise(model.confusion.counts) : null;
  return (
    <div className="flex flex-col">
      <table className="-mx-[3px] w-[calc(100%+6px)] table-fixed border-separate border-spacing-[3px]">
        <caption className="caption-bottom px-[3px] pt-2 text-left text-[12px] leading-4 text-text-tertiary">
          {MATRIX_COPY.caption}
        </caption>
        <colgroup>
          <col className="w-[88px] max-sm:w-[76px]" />
          {classes.map((label) => (
            <col key={label} />
          ))}
        </colgroup>
        <thead>
          <tr>
            <td className="text-left align-bottom text-[11px] leading-[14px] text-text-tertiary">
              разметка ↓
            </td>
            <th
              scope="colgroup"
              colSpan={classes.length}
              className="pb-0.5 text-left text-[11px] leading-[14px] font-normal text-text-tertiary"
            >
              прогноз →
            </th>
          </tr>
          <tr>
            <td />
            {classes.map((label) => (
              <th
                key={label}
                scope="col"
                className="px-0.5 pb-1 text-center align-bottom text-[11px] leading-[14px] font-medium hyphens-auto text-text-secondary"
              >
                {label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {classes.map((label, row) => (
            <tr key={label}>
              <th
                scope="row"
                className="pr-1.5 text-right text-[12px] leading-4 font-medium text-text-secondary"
              >
                {label}
              </th>
              {classes.map((column, col) => {
                const share = shares?.[row]?.[col] ?? null;
                return (
                  <td
                    key={column}
                    style={share !== null ? cellStyle(share) : undefined}
                    className={cn(
                      "h-10 text-center font-mono text-[12px] leading-4 max-sm:h-9",
                      share === null && "bg-surface-sunken text-text-tertiary",
                      row === col && styles.diagonal,
                      row === col && "font-semibold",
                    )}
                  >
                    {share === null ? DASH : formatShare(share)}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="mt-1.5 text-[12px] leading-4 text-text-tertiary">{MATRIX_COPY.grouping}</p>
    </div>
  );
}
